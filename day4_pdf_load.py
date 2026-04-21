from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

#替换成你的PDF路径
pdf_path = "./15data/15th_plan.pdf"

#加载PDF
loader = PyPDFLoader(pdf_path)
documents = loader.load()
print(f"共加载{len(documents)}页")

#切分文本
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,        #每块最多1000个字符
    chunk_overlap=100       #块之间重叠100个字符，保持上下文连贯
)
chunks = text_splitter.split_documents(documents)
print(f"共切分为{len(chunks)}个文本块")

#打印前3块内容，看看切出效果
for i, chunk in enumerate(chunks[:3]):
    print(f"\n====第{i+1}块====")
    print(chunk.page_content[:200]+"...")  #只打印前200字符，避免输出过长