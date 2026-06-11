from graph import beta_graph

def main():
    print("Menggambar arsitektur DAG Beta Agentic...")
    
    try:
        # Mengambil graf dan merendernya menjadi data gambar PNG via API Mermaid
        gambar_png = beta_graph.get_graph().draw_mermaid_png()

        # Menyimpan data tersebut ke dalam file fisik
        with open("arsitektur_dag_beta_agentic.png", "wb") as f:
            f.write(gambar_png)

        print("✅ Diagram berhasil disimpan sebagai 'arsitektur_dag_beta_agentic.png' di folder ini!")
        
    except Exception as e:
        print(f"❌ Gagal membuat diagram. Pastikan koneksi internet aktif karena draw_mermaid_png butuh akses API eksternal.")
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
