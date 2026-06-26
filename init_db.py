import sqlite3

#创建数据库并建表和员工薪资表
conn = sqlite3.connect('company.db')
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS employees
                  (id INTEGER PRIMARY KEY, name TEXT, department TEXT, salary INTEGER, hire_date TEXT)''')

#插入测试数据
data = [
    ("张三", "研发部", 15000, "2025-03-01"),
    ("李四", "研发部", 20000, "2024-07-15"),
    ("王五", "市场部", 12000, "2025-01-10"),
    ("赵六", "人事部", 13000, "2024-11-20"),
    ("孙七", "研发部", 18000, "2023-06-01"),
    ("周八", "市场部", 11000, "2025-05-01"),
    ("吴九", "财务部", 14000, "2024-09-10"),
    ("郑十", "研发部", 17000, "2025-02-18"),
]
cursor.executemany("INSERT OR IGNORE INTO employees VALUES (NULL, ?, ?, ?, ?)", data)
conn.commit()
conn.close()
print("数据库初始化完成，测试数据已插入。")