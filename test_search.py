import sys
import os

# Add beta-agentic to path so we can import tools
sys.path.insert(0, r"c:\Users\Ammar\Projek\agentic-ai\beta-agentic")
from tools import RAGEngine

query = "Dinamika Litosfer"
print(f"Querying: {query}")
result1 = RAGEngine.unified_search(query, "bacaan")
print("Without filter, total found:", len(result1["text"]))
if result1["text"]:
    print("Sample metadata:", result1["text"][0]["metadata"])

result2 = RAGEngine.unified_search(query, "bacaan", mapel="IPS", kelas=10)
print("With filter (kelas=10, mapel=IPS):", len(result2["text"]))

result3 = RAGEngine.unified_search(query, "bacaan", mapel="IPS", kelas="Kelas 10")
print("With string filter (kelas='Kelas 10'):", len(result3["text"]))
