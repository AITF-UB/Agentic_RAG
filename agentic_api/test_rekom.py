import asyncio
import os
import json
from langchain_core.messages import SystemMessage, HumanMessage
from agentic_api.llm import get_llm
from agentic_api.graph import env

async def main():
    llm = get_llm()
    bound_llm = llm.bind(response_format={"type": "json_object"})

    def load_prompt(template_name: str, **kwargs) -> str:
        template = env.get_template(template_name)
        return template.render(**kwargs)

    sys_msg = SystemMessage(content=(
        "You are a strict AI Study Recommender. "
        "You MUST return ONLY a valid raw JSON object — no markdown, no explanation. "
        "NEVER hallucinate bundle_id, mapel_label, elemen_label, or materi. "
        "ONLY use values that are EXACTLY listed in the Available or In_Progress_Ids materials provided by the user. "
        "If the source material has null or empty materi, you MUST set materi to its elemen_label in your response."
    ))

    prompt = load_prompt(
        "rekomendasi.j2",
        available=[{"bundle_id": "7", "mapel_label": "Sosiologi", "elemen_label": "Sosiologi sebagai Ilmu", "materi": "Sosiologi sebagai Ilmu", "atp": ["Peserta didik mampu menggunakan hasil analisis sosial sebagai dasar rekomendasi solusi terhadap masalah sosial.", "Peserta didik mampu mengaitkan konsep sosiologi, sejarah, geografi, dan ekonomi untuk menganalisis fenomena sosial di sekitar.", "Peserta didik mampu membedakan pendekatan kualitatif, kuantitatif, dan campuran dalam penelitian sosial.", "Peserta didik memahami sosiologi sebagai ilmu yang mengkaji masyarakat secara kritis, analitis, kreatif, dan solutif."]}],
        in_progress=[],
        complete=[],
    )

    print("--- SYS MSG ---")
    print(sys_msg.content)
    print("\n--- HUMAN PROMPT ---")
    print(prompt)
    print("\n--- INVOKING LLM ---")
    res = await bound_llm.ainvoke([sys_msg, HumanMessage(content=prompt)])
    print("--- RAW CONTENT ---")
    print(repr(res.content))

if __name__ == "__main__":
    asyncio.run(main())
