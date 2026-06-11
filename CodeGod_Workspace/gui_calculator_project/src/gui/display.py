from tkinter import *
import math

class Display:
    def __init__(self, root):
        self.root = root
        self.result_label = Label(root, text='0', font=('Arial', 24))
        self.result_label.pack()
        self.entry = Entry(root)
        self.entry.pack()
        self.add_button = Button(root, text='+', command=self.add)
        self.add_button.pack()
        self.subtract_button = Button(root, text='-', command=self.subtract)
        self.subtract_button.pack()
        self.multiply_button = Button(root, text='*', command=self.multiply)
        self.multiply_button.pack()
        self.divide_button = Button(root, text='/', command=self.divide)
        self.divide_button.pack()

    def add(self):
        num1 = float(self.entry.get())
        result = num1 + math.sqrt(num1)  # Add square root to the number
        self.result_label.config(text=str(result))

    def subtract(self):
        num1 = float(self.entry.get())
        result = num1 - math.sqrt(num1)  # Subtract square root from the number
        self.result_label.config(text=str(result))

    def multiply(self):
        num1 = float(self.entry.get())
        result = num1 * math.sqrt(num1)  # Multiply by square root of the number
        self.result_label.config(text=str(result))

    def divide(self):
        num1 = float(self.entry.get())
        if num1 != 0:
            result = num1 / math.sqrt(num1)  # Divide by square root of the number
            self.result_label.config(text=str(result))
        else:
            messagebox.showerror('Error', 'Cannot divide by zero')