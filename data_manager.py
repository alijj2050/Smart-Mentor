import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, Menu
import sqlite3
import re
from datetime import datetime
from typing import List, Tuple  # اضافه کردن این خط

class DatabaseManager:
    DB_NAME = "mentor.db"

    @staticmethod
    def connect():
        return sqlite3.connect(DatabaseManager.DB_NAME)

    @staticmethod
    def fetch_all(query: str, params: tuple = ()) -> List[tuple]:
        with DatabaseManager.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchall()

    @staticmethod
    def execute(query: str, params: tuple = ()):
        with DatabaseManager.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()

class RestaurantManagementApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Restaurant Management System")
        self.root.geometry("1200x800")

        self.tab_control = ttk.Notebook(self.root)
        self.tab_qa = ttk.Frame(self.tab_control)
        self.tab_menu = ttk.Frame(self.tab_control)
        self.tab_parse = ttk.Frame(self.tab_control)

        self.tab_control.add(self.tab_qa, text="Manage Q&A")
        self.tab_control.add(self.tab_menu, text="Manage Menu")
        self.tab_control.add(self.tab_parse, text="Parse Text")
        self.tab_control.pack(expand=1, fill="both")

        self.setup_qa_tab()
        self.setup_menu_tab()
        self.setup_parse_tab()

    def setup_qa_tab(self):
        frame = tk.Frame(self.tab_qa)
        frame.pack(pady=10)

        tk.Label(frame, text="Question:").grid(row=0, column=0, padx=5, pady=5)
        self.entry_question = tk.Entry(frame, width=50)
        self.entry_question.grid(row=0, column=1, padx=5, pady=5)

        tk.Label(frame, text="Answer:").grid(row=1, column=0, padx=5, pady=5)
        self.entry_answer = tk.Entry(frame, width=50)
        self.entry_answer.grid(row=1, column=1, padx=5, pady=5)

        tk.Button(frame, text="Add/Update Q&A", command=self.add_qa).grid(row=2, column=0, columnspan=2, pady=10)

        self.tree_qa = self.create_treeview(self.tab_qa, ["Question", "Answer", "Timestamp"])
        tk.Button(self.tab_qa, text="Delete Selected", command=self.delete_qa).pack(pady=5)

    def setup_menu_tab(self):
        frame = tk.Frame(self.tab_menu)
        frame.pack(pady=10)

        tk.Label(frame, text="Item Name:").grid(row=0, column=0, padx=5, pady=5)
        self.entry_name = tk.Entry(frame, width=30)
        self.entry_name.grid(row=0, column=1, padx=5, pady=5)

        tk.Label(frame, text="Price (Toman):").grid(row=1, column=0, padx=5, pady=5)
        self.entry_price = tk.Entry(frame, width=30)
        self.entry_price.grid(row=1, column=1, padx=5, pady=5)

        tk.Label(frame, text="Description:").grid(row=2, column=0, padx=5, pady=5)
        self.entry_description = tk.Entry(frame, width=30)
        self.entry_description.grid(row=2, column=1, padx=5, pady=5)

        tk.Button(frame, text="Add/Update Menu Item", command=self.add_menu_item).grid(row=3, column=0, columnspan=2, pady=10)

        self.tree_menu = self.create_treeview(self.tab_menu, ["Name", "Price", "Description", "Timestamp"])
        tk.Button(self.tab_menu, text="Delete Selected", command=self.delete_menu_item).pack(pady=5)

    def setup_parse_tab(self):
        frame = tk.Frame(self.tab_parse)
        frame.pack(pady=10)

        tk.Label(frame, text="Enter the text to parse:").grid(row=0, column=0, padx=5, pady=5)
        self.text_input = scrolledtext.ScrolledText(frame, width=100, height=20)
        self.text_input.grid(row=1, column=0, padx=5, pady=5)

        tk.Button(frame, text="Parse and Save/Update", command=self.parse_and_save).grid(row=2, column=0, pady=10)

    def create_treeview(self, parent, columns):
        tree = ttk.Treeview(parent, columns=columns, show="headings", height=20)
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=200 if col != "Description" else 400)
        tree.pack(pady=10)
        return tree

    def add_qa(self):
        question = self.entry_question.get().strip()
        answer = self.entry_answer.get().strip()
        if question and answer:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            existing = DatabaseManager.fetch_all("SELECT timestamp FROM qa WHERE question = ?", (question,))
            if existing:
                existing_timestamp = existing[0][0]
                if timestamp > existing_timestamp:
                    DatabaseManager.execute("DELETE FROM qa WHERE question = ?", (question,))
                    DatabaseManager.execute("INSERT INTO qa (question, answer, timestamp) VALUES (?, ?, ?)", (question, answer, timestamp))
            else:
                DatabaseManager.execute("INSERT INTO qa (question, answer, timestamp) VALUES (?, ?, ?)", (question, answer, timestamp))
            self.refresh_qa_list()
            self.entry_question.delete(0, tk.END)
            self.entry_answer.delete(0, tk.END)
            messagebox.showinfo("Success", "Question and answer added/updated.")
        else:
            messagebox.showwarning("Warning", "Please fill in both fields.")

    def delete_qa(self):
        selected = self.tree_qa.selection()
        if selected:
            item_id = selected[0]
            item_value = self.tree_qa.item(item_id, "values")[0]
            DatabaseManager.execute("DELETE FROM qa WHERE question = ?", (item_value,))
            self.refresh_qa_list()
            messagebox.showinfo("Success", "Item deleted successfully.")
        else:
            messagebox.showwarning("Warning", "Please select an item.")

    def refresh_qa_list(self):
        for row in self.tree_qa.get_children():
            self.tree_qa.delete(row)
        data = DatabaseManager.fetch_all("SELECT question, answer, timestamp FROM qa")
        for record in data:
            self.tree_qa.insert("", tk.END, values=record)

    def add_menu_item(self):
        name = self.entry_name.get().strip()
        price = self.entry_price.get().strip()
        description = self.entry_description.get().strip()
        if name and price.isdigit() and description:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            existing = DatabaseManager.fetch_all("SELECT timestamp FROM menu WHERE name = ?", (name,))
            if existing:
                existing_timestamp = existing[0][0]
                if timestamp > existing_timestamp:
                    DatabaseManager.execute("DELETE FROM menu WHERE name = ?", (name,))
                    DatabaseManager.execute("INSERT INTO menu (name, price, description, timestamp) VALUES (?, ?, ?, ?)", (name, int(price), description, timestamp))
            else:
                DatabaseManager.execute("INSERT INTO menu (name, price, description, timestamp) VALUES (?, ?, ?, ?)", (name, int(price), description, timestamp))
            self.refresh_menu_list()
            self.clear_menu_entries()
            messagebox.showinfo("Success", "Menu item added/updated.")
        else:
            messagebox.showwarning("Warning", "Please fill in all fields with valid data.")

    def delete_menu_item(self):
        selected = self.tree_menu.selection()
        if selected:
            item_id = selected[0]
            item_value = self.tree_menu.item(item_id, "values")[0]
            DatabaseManager.execute("DELETE FROM menu WHERE name = ?", (item_value,))
            self.refresh_menu_list()
            messagebox.showinfo("Success", "Item deleted successfully.")
        else:
            messagebox.showwarning("Warning", "Please select an item.")

    def refresh_menu_list(self):
        for row in self.tree_menu.get_children():
            self.tree_menu.delete(row)
        data = DatabaseManager.fetch_all("SELECT name, price || ' Toman', description, timestamp FROM menu")
        for record in data:
            self.tree_menu.insert("", tk.END, values=record)

    def clear_menu_entries(self):
        self.entry_name.delete(0, tk.END)
        self.entry_price.delete(0, tk.END)
        self.entry_description.delete(0, tk.END)

    def parse_and_save(self):
        text = self.text_input.get("1.0", tk.END).strip()
        if not text:
            messagebox.showwarning("Warning", "Please enter text.")
            return

        pattern = r"(.+?)\n(.+?)\n(\d{1,3}(?:,\d{3})*) تومان"
        matches = re.findall(pattern, text)
        if not matches:
            messagebox.showwarning("Warning", "No valid menu items found.")
            return

        for name, description, price in matches:
            price = int(price.replace(",", ""))
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            DatabaseManager.execute(
                "INSERT OR REPLACE INTO menu (name, price, description, timestamp) VALUES (?, ?, ?, ?)",
                (name.strip(), price, description.strip(), timestamp),
            )
        self.refresh_menu_list()
        messagebox.showinfo("Success", "Menu items parsed and saved/updated.")

if __name__ == "__main__":
    root = tk.Tk()
    app = RestaurantManagementApp(root)
    root.mainloop()