from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings 
from openai import OpenAI
import yaml

# 1. 从 config.yaml 读取配置
with open("config.yaml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

# 2. 加载向量库
embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2",
    model_kwargs={'device': 'cpu'},
    encode_kwargs={'normalize_embeddings': True}
)
vector_store = FAISS.load_local(
    "./faiss_index", embeddings, allow_dangerous_deserialization=True
)

# 3. 大模型客户端
client = OpenAI(
    api_key=config["aliyun_api_key"],
    base_url=config["aliyun_base_url"]
)

# 4. 问答函数
def ask(question):
    # 检索最相关的3个文本块
    docs = vector_store.similarity_search(question, k=3)

    # 拼接上下文
    context = "\n\n".join([doc.page_content for doc in docs])

    # 构建提示词
    prompt = f"""请根据以下参考资料回答问题。如果资料中没有答案，请回答"根据现有资料无法回答"。

参考资料：
{context}

问题：{question}

回答："""

    # 调用大模型
    response = client.chat.completions.create(
        model="qwen-plus",
        messages=[{"role": "user", "content": prompt}]
    )

    return response.choices[0].message.content, docs

# 5. 测试
question = "十五五规划中提到了哪些未来产业？"
answer, sources = ask(question)

print("=" * 50)
print(f"问题：{question}")
print("=" * 50)
print(f"回答：{answer}")
print("=" * 50)
print("参考来源：")
for i, doc in enumerate(sources, 1):
    print(f"\n来源 {i}：")
    print(doc.page_content[:200] + "...")