import os
import re
import requests as _req_lib
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage
from huggingface_hub import InferenceClient
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.outputs import ChatResult, ChatGeneration
from dotenv import load_dotenv

load_dotenv()


# =====================================================================
# VLLM AUTO-ROUTING — Pilih host yang paling longgar berdasarkan /metrics
# =====================================================================
def _parse_vllm_metric(metrics_text: str, metric_name: str) -> float:
    """Parse satu nilai dari output Prometheus plain-text vLLM /metrics."""
    for line in metrics_text.splitlines():
        if line.startswith(metric_name + "{") or line.startswith(metric_name + " "):
            # Format: metric_name{...} <nilai> atau metric_name <nilai>
            parts = line.rsplit(" ", 1)
            if len(parts) == 2:
                try:
                    return float(parts[1])
                except ValueError:
                    pass
    return 0.0


def get_available_llm_host(hosts_env: str, timeout: float = 2.0) -> str:
    """
    Memilih host vLLM yang paling kosong kapasitasnya dari daftar host.

    Args:
        hosts_env: String URL host, dipisah ';'. Contoh:
                   "http://gpu1:8000/v1;http://gpu2:8000/v1"
        timeout:   Batas waktu (detik) saat nge-ping /metrics tiap host.

    Returns:
        URL host (dengan /v1 jika ada) yang paling sedikit bebannya.
        Jika semua host sibuk atau /metrics tidak dapat dijangkau,
        kembalikan host pertama sebagai default.

    Logika routing (sesuai saran Mas Anjas):
      1. Looping tiap host dalam urutan.
      2. GET {host_root}/metrics dengan timeout singkat.
         (strip /v1 karena vLLM expose metrics di root, bukan /v1/metrics)
      3. Cek `vllm:num_requests_running` + `vllm:num_requests_waiting`.
      4. Kalau total == 0 → host ini kosong, langsung pakai.
      5. Kalau semua penuh → fallback ke host pertama.
    """
    raw_hosts = [h.strip() for h in hosts_env.split(";") if h.strip()]
    if not raw_hosts:
        return ""

    default_host = raw_hosts[0]
    best_host = None
    best_load = float("inf")

    for host in raw_hosts:
        # base = URL lengkap yg akan dikembalikan ke ChatOpenAI (misal: http://ip:8000/v1)
        base = host.rstrip("/")
        # metrics_base = URL root tanpa /v1 untuk ping /metrics
        # vLLM expose /metrics di root path, BUKAN di /v1/metrics
        metrics_base = base[:-3] if base.endswith("/v1") else base
        try:
            resp = _req_lib.get(f"{metrics_base}/metrics", timeout=timeout)
            if resp.status_code != 200:
                print(f"[LLM Router] {metrics_base}/metrics returned {resp.status_code}, skip.")
                continue

            text = resp.text
            running = _parse_vllm_metric(text, "vllm:num_requests_running")
            waiting = _parse_vllm_metric(text, "vllm:num_requests_waiting")
            total_load = running + waiting

            print(f"[LLM Router] {base} → running={running}, waiting={waiting}, total={total_load}")

            if total_load == 0:
                # Host kosong — langsung pilih ini, kembalikan URL lengkap (dengan /v1)
                print(f"[LLM Router] ✓ Pilih {base} (kosong)")
                return base

            if total_load < best_load:
                best_load = total_load
                best_host = base

        except _req_lib.exceptions.RequestException as e:
            print(f"[LLM Router] Gagal ping {metrics_base}/metrics: {e}")
            continue

    # Tidak ada host yang kosong — pakai yang paling sedikit bebannya
    chosen = best_host or default_host
    print(f"[LLM Router] Semua host sibuk. Fallback ke {chosen} (load={best_load})")
    return chosen

# =====================================================================
# 1. HUGGING FACE INFERENCE (CUSTOM CLASS)
# =====================================================================
class HFChatModel(BaseChatModel):
    client: InferenceClient = None
    model_id: str = os.getenv("HF_MODEL_ID", "meta-llama/Llama-3.1-8B-Instruct")
    temperature: float = 0.2
    max_tokens: int = int(os.getenv("MAX_TOKEN", 8192))

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        hf_token = os.getenv("HF_TOKEN")
        self.client = InferenceClient(model=self.model_id, token=hf_token)

    @property
    def _llm_type(self) -> str:
        return "hf-chat"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        hf_msgs = []
        for msg in messages:
            if isinstance(msg, SystemMessage):
                hf_msgs.append({"role": "system", "content": msg.content})
            elif isinstance(msg, HumanMessage):
                hf_msgs.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                hf_msgs.append({"role": "assistant", "content": msg.content})
            else:
                hf_msgs.append({"role": "user", "content": str(msg.content)})
        
        response = self.client.chat_completion(
            messages=hf_msgs,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            stop=stop
        )
        output_text = response.choices[0].message.content
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=output_text))])


# =====================================================================
# FACTORY PATTERN: GET LLM BASED ON .ENV
# =====================================================================
def get_llm():
    provider = os.getenv("LLM_PROVIDER", "huggingface").lower().strip()

    if provider == "bedrock":
        import boto3
        from langchain_aws import ChatBedrockConverse
        
        bedrock_client = boto3.client(
            service_name="bedrock-runtime",
            region_name=os.getenv("BEDROCK_REGION", "us-east-1"),
            endpoint_url=os.getenv("BEDROCK_ENDPOINT_URL") or None,
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY")
        )
        return ChatBedrockConverse(
            client=bedrock_client,
            model_id=os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0"),
            temperature=0.3,
            max_tokens=int(os.getenv("MAX_TOKEN", 4000))
        )

    elif provider == "runpod":
        from langchain_openai import ChatOpenAI
        
        return ChatOpenAI(
            openai_api_base=os.getenv("RUNPOD_ENDPOINT_URL"),
            openai_api_key=os.getenv("RUNPOD_API_KEY", "empty"),
            model_name=os.getenv("RUNPOD_MODEL_ID", "meta-llama/Meta-Llama-3-8B-Instruct"),
            temperature=0.3,
            max_tokens=int(os.getenv("MAX_TOKEN", 4000)),
            model_kwargs={"response_format": {"type": "json_object"}},
            extra_body={"chat_template_kwargs": {"enable_thinking": False}}
        )

    elif provider == "tim2_vllm":
        from langchain_openai import ChatOpenAI

        # Mendukung multi-host (dipisah ';'). Fungsi get_available_llm_host()
        # akan memilih host yang paling kosong secara real-time berdasarkan
        # GET /metrics dari vLLM (saran Mas Anjas).
        hosts_env = os.getenv("TIM2_VLLM_ENDPOINT", "")

        if ";" in hosts_env:
            # Mode multi-host: pilih host terbaik via /metrics
            endpoint = get_available_llm_host(hosts_env)
        else:
            endpoint = hosts_env.strip()

        if endpoint:
            if not endpoint.startswith("http://") and not endpoint.startswith("https://"):
                endpoint = "http://" + endpoint
            if endpoint.endswith("/chat/completions"):
                endpoint = endpoint.replace("/chat/completions", "")

        # Endpoint dari Tim 2 (menggunakan format OpenAI-compatible dari vLLM)
        return ChatOpenAI(
            openai_api_base=endpoint,
            openai_api_key="empty",  # Karena Tim 2 bilang tidak pakai token/auth
            model_name=os.getenv("TIM2_MODEL_ID", "aitf-ub-2026/ub-sr-02-qwen3.5-9b-base-sft-v2"),
            temperature=float(os.getenv("TIM2_TEMPERATURE", "0.2")),
            max_tokens=int(os.getenv("MAX_TOKEN", 4096)),
            streaming=True,  # Bypass Cloudflare 100s timeout
            max_retries=1,   # Mencegah retry berulang-ulang yang bikin antrean vLLM meledak
            model_kwargs={"response_format": {"type": "json_object"}},
            extra_body={"chat_template_kwargs": {"enable_thinking": False}}
        )

    elif provider == "kaggle_vllm":
        from langchain_openai import ChatOpenAI
        
        # vLLM di Kaggle menyediakan endpoint OpenAI-compatible
        return ChatOpenAI(
            openai_api_base=os.getenv("NGROK_KAGGLE_VLLM"),
            openai_api_key="empty", # vLLM lokal tidak butuh api key
            model_name=os.getenv("KAGGLE_VLLM_MODEL_ID", "AITF-SR-02/ub-sr-02-qwen3.5-9b-base-5k-CPT-SFT-v2"),
            temperature=0.3,
            max_tokens=int(os.getenv("MAX_TOKEN", 4000)),
            model_kwargs={"response_format": {"type": "json_object"}},
            extra_body={"chat_template_kwargs": {"enable_thinking": False}}
        )

    elif provider == "kaggle_ollama":
        from langchain_community.chat_models import ChatOllama
        
        return ChatOllama(
            base_url=os.getenv("NGROK_KAGGLE_OLLAMA"),
            model=os.getenv("KAGGLE_OLLAMA_MODEL_ID", "qwen3.5:9b"), 
            temperature=0.3,
            format="json"
        )

    elif provider == "kaggle_llamacpp":
        from langchain_openai import ChatOpenAI
        
        # llama-server di Kaggle menyediakan endpoint OpenAI-compatible di /v1
        endpoint = os.getenv("NGROK_KAGGLE_LLAMACPP")
        if endpoint and not endpoint.endswith("/v1"):
            endpoint = endpoint + "/v1"
            
        return ChatOpenAI(
            openai_api_base=endpoint,
            openai_api_key="llama-cpp",
            model_name=os.getenv("KAGGLE_LLAMACPP_MODEL_ID", "unsloth/Qwen3.6-35B-A3B-MTP-GGUF:UD-Q4_K_M"),
            temperature=0.3,
            max_tokens=int(os.getenv("MAX_TOKEN", 4000)),
            model_kwargs={"response_format": {"type": "json_object"}},
            extra_body={"chat_template_kwargs": {"enable_thinking": False}}
        )

    else:
        # Default fallback ke Hugging Face Inference
        return HFChatModel()

# =====================================================================
# FACTORY PATTERN: GET EVAL LLM BASED ON .ENV
# =====================================================================
def get_eval_llm():
    """Mendapatkan instansiasi LLM khusus untuk Evaluator."""
    # Jika tidak ada setting khusus untuk EVAL, fallback ke LLM utama
    provider = os.getenv("EVAL_LLM_PROVIDER")
    if not provider:
        return get_llm()
        
    provider = provider.lower().strip()

    if provider == "huggingface":
        # Gunakan HFChatModel (dengan EVAL_HF_MODEL_ID khusus atau fallback ke HF biasa)
        class EvalHFChatModel(HFChatModel):
            model_id: str = os.getenv("EVAL_HF_MODEL_ID", os.getenv("HF_MODEL_ID", "meta-llama/Llama-3.1-8B-Instruct"))
            temperature: float = 0.0 # Evaluator sebaiknya temperaturnya 0
        return EvalHFChatModel()
    elif provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            openai_api_key=os.getenv("EVAL_OPENAI_API_KEY"),
            model_name=os.getenv("EVAL_OPENAI_MODEL_ID", "gpt-4o-mini"),
            temperature=0.0,
            max_tokens=3000,
            model_kwargs={"response_format": {"type": "json_object"}}
        )
    elif provider == "bedrock":
        import boto3
        from langchain_aws import ChatBedrockConverse
        bedrock_client = boto3.client(
            service_name="bedrock-runtime",
            region_name=os.getenv("EVAL_BEDROCK_REGION") or os.getenv("BEDROCK_REGION", "us-east-1"),
            endpoint_url=os.getenv("EVAL_BEDROCK_ENDPOINT_URL") or os.getenv("BEDROCK_ENDPOINT_URL") or None,
            aws_access_key_id=os.getenv("EVAL_AWS_ACCESS_KEY_ID") or os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("EVAL_AWS_SECRET_ACCESS_KEY") or os.getenv("AWS_SECRET_ACCESS_KEY")
        )
        return ChatBedrockConverse(
            client=bedrock_client,
            model_id=os.getenv("EVAL_BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0"),
            temperature=0.0,
            max_tokens=3000
        )
    elif provider == "runpod":
        from langchain_openai import ChatOpenAI
        endpoint = os.getenv("EVAL_RUNPOD_ENDPOINT_URL") or os.getenv("RUNPOD_ENDPOINT_URL")
        if endpoint and endpoint.endswith("/chat/completions"):
            endpoint = endpoint.replace("/chat/completions", "")
            
        return ChatOpenAI(
            openai_api_base=endpoint,
            openai_api_key=os.getenv("EVAL_RUNPOD_API_KEY") or os.getenv("RUNPOD_API_KEY", "empty"),
            model_name=os.getenv("EVAL_RUNPOD_MODEL_ID", "qwen/qwen3-8b"),
            temperature=0.0,
            max_tokens=3000,
            model_kwargs={"response_format": {"type": "json_object"}},
            extra_body={"chat_template_kwargs": {"enable_thinking": False}}
        )
    elif provider == "vllm":
        from langchain_openai import ChatOpenAI
        endpoint = os.getenv("EVAL_VLLM_ENDPOINT") or os.getenv("VLLM_ENDPOINT")
        if endpoint:
            if not endpoint.startswith("http://") and not endpoint.startswith("https://"):
                endpoint = "http://" + endpoint
            if endpoint.endswith("/chat/completions"):
                endpoint = endpoint.replace("/chat/completions", "")
                
        return ChatOpenAI(
            openai_api_base=endpoint,
            openai_api_key="empty",
            model_name=os.getenv("EVAL_VLLM_MODEL_ID") or os.getenv("VLLM_MODEL_ID", "Qwen/Qwen2.5-72B-Instruct"),
            temperature=0.0,
            max_tokens=3000,
            model_kwargs={"response_format": {"type": "json_object"}},
            extra_body={"chat_template_kwargs": {"enable_thinking": False}}
        )
    elif provider == "kaggle_llamacpp":
        from langchain_openai import ChatOpenAI
        endpoint = os.getenv("EVAL_NGROK_KAGGLE_LLAMACPP") or os.getenv("NGROK_KAGGLE_LLAMACPP")
        if endpoint and not endpoint.endswith("/v1"):
            endpoint = endpoint + "/v1"
            
        return ChatOpenAI(
            openai_api_base=endpoint,
            openai_api_key="llama-cpp",
            model_name=os.getenv("EVAL_KAGGLE_LLAMACPP_MODEL_ID", "unsloth/qwen3.6"),
            temperature=0.0,
            max_tokens=3000,
            model_kwargs={"response_format": {"type": "json_object"}},
            extra_body={"chat_template_kwargs": {"enable_thinking": False}}
        )
    elif provider == "tim2_vllm":
        from langchain_openai import ChatOpenAI
        endpoint = os.getenv("EVAL_TIM2_VLLM_ENDPOINT") or os.getenv("TIM2_VLLM_ENDPOINT")
        if endpoint:
            if not endpoint.startswith("http://") and not endpoint.startswith("https://"):
                endpoint = "http://" + endpoint
            if endpoint.endswith("/chat/completions"):
                endpoint = endpoint.replace("/chat/completions", "")
                
        return ChatOpenAI(
            openai_api_base=endpoint,
            openai_api_key="empty",
            model_name=os.getenv("EVAL_TIM2_MODEL_ID") or os.getenv("TIM2_MODEL_ID", "aitf-ub-2026/ub-sr-02-qwen3.5-9b-base-sft-v2"),
            temperature=0.0,  # Evaluator harus deterministik (temperature 0)
            max_tokens=3000,
            model_kwargs={"response_format": {"type": "json_object"}},
            extra_body={"chat_template_kwargs": {"enable_thinking": False}}
        )
    else:
        return get_llm()
