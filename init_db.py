"""
init_db.py — 企业数据库初始化脚本
===================================
用途：创建 SQLite 数据库 company.db，建立 employees 表并插入测试数据。

数据结构：
    employees 表
    ├── id           INTEGER PRIMARY KEY
    ├── name         TEXT     员工姓名
    ├── department   TEXT     所属部门
    ├── salary       INTEGER  月薪（元）
    └── hire_date    TEXT     入职日期（YYYY-MM-DD）

使用方式：
    python init_db.py          直接运行，创建/重置数据库
    from init_db import init_database; init_database()  作为模块调用

注意：重复运行使用 INSERT OR IGNORE，不会产生重复数据。
"""

import os
import sqlite3


def init_database(db_path: str = None) -> str:
    """创建数据库并初始化员工薪资表。

    在指定路径创建 company.db（默认在脚本同目录），
    建立 employees 表并插入 8 条测试数据。
    若表已存在则跳过建表，若主键冲突则跳过插入。

    参数:
        db_path: 数据库文件路径，默认为脚本所在目录下的 company.db

    返回:
        str: 数据库文件的绝对路径

    异常:
        sqlite3.Error: 数据库操作失败时抛出，调用方应捕获处理
    """
    if db_path is None:
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'company.db')

    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 建表
        cursor.execute('''CREATE TABLE IF NOT EXISTS employees
                          (id INTEGER PRIMARY KEY,
                           name TEXT,
                           department TEXT,
                           salary INTEGER,
                           hire_date TEXT)''')

        # 测试数据
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
        print(f"数据库初始化完成，{len(data)} 条测试数据已就绪。")
        return os.path.abspath(db_path)

    except sqlite3.Error as e:
        print(f"数据库初始化失败: {e}")
        raise
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    init_database()
