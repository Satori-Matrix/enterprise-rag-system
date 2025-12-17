#!/usr/bin/env python
import os,sys,asyncio,httpx
from dotenv import load_dotenv
load_dotenv()
OLLAMA=os.getenv("LLM_BINDING_HOST","http://ollama:11434")
LLM=os.getenv("LLM_MODEL","qwen2.5:7b")
VLM=os.getenv("VLM_MODEL","qwen2.5vl:latest")
EMB=os.getenv("EMBEDDING_MODEL","nomic-embed-text")
DIM=int(os.getenv("EMBEDDING_DIM","768"))
WDIR=os.getenv("WORKING_DIR","./rag_storage")
ODIR=os.getenv("OUTPUT_DIR","./output")
from raganything import RAGAnything,RAGAnythingConfig
from lightrag.utils import EmbeddingFunc
async def ogen(model,prompt,sys_p=None,imgs=None):
    async with httpx.AsyncClient(timeout=600) as c:
        p={"model":model,"prompt":prompt,"stream":False,"options":{"temperature":0,"num_ctx":4096}}
        if sys_p:p["system"]=sys_p
        if imgs:p["images"]=imgs
        r=await c.post(f"{OLLAMA}/api/generate",json=p)
        return r.json().get("response","")
async def oemb(texts):
    embs=[]
    async with httpx.AsyncClient(timeout=300) as c:
        for t in texts:
            r=await c.post(f"{OLLAMA}/api/embed",json={"model":EMB,"input":t})
            embs.append(r.json()["embeddings"][0])
    return embs
async def llm_fn(prompt,system_prompt=None,**kw):
    return await ogen(LLM,prompt,system_prompt)
async def vlm_fn(prompt,system_prompt=None,image_data=None,**kw):
    if image_data:return await ogen(VLM,prompt,system_prompt,[image_data])
    return await llm_fn(prompt,system_prompt)
async def process(fpath):
    print(f"Processing:{fpath}")
    cfg=RAGAnythingConfig(working_dir=WDIR,parser="mineru",parse_method="auto",enable_image_processing=True,enable_table_processing=True,enable_equation_processing=True)
    rag=RAGAnything(config=cfg,llm_model_func=llm_fn,vision_model_func=vlm_fn,embedding_func=EmbeddingFunc(embedding_dim=DIM,max_token_size=8192,func=oemb))
    await rag.process_document_complete(file_path=fpath,output_dir=ODIR,parse_method="auto",display_stats=True)
    print("Done!")
if __name__=="__main__":
    if len(sys.argv)<2:print("Usage:python ingest.py <file>");sys.exit(1)
    asyncio.run(process(sys.argv[1]))
