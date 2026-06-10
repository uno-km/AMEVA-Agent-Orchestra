# Importing necessary libraries
from tkinter import *

# Function to clear the entry
def clear_entry():
    entry.delete(0, END)

# Function to add two numbers
def add():
    try:
        num1 = float(entry1.get())
        num2 = float(entry2.get())
        result = num1 + num2
        entry.delete(0, END)
        entry.insert(0, str(result))
    except ValueError:
        entry.insert(0, 'Invalid input')

# Function to subtract two numbers
def subtract():
    try:
        num1 = float(entry1.get())
        num2 = float(entry2.get())
        result = num1 - num2
        entry.delete(0, END)
        entry.insert(0, str(result))
    except ValueError:
        entry.insert(0, 'Invalid input')

# Function to multiply two numbers
def multiply():
    try:
        num1 = float(entry1.get())
        num2 = float(entry2.get())
        result = num1 * num2
        entry.delete(0, END)
        entry.insert(0, str(result))
    except ValueError:
        entry.insert(0, 'Invalid input')

# Function to divide two numbers
def divide():
    try:
        num1 = float(entry1.get())
        num2 = float(entry2.get())
        result = num1 / num2
        entry.delete(0, END)
        entry.insert(0, str(result))
    except ValueError:
        entry.insert(0, 'Invalid input')
    except ZeroDivisionError:
        entry.insert(0, 'Cannot divide by zero')

# Main function to run the application
if __name__ == '__main__':
    # Creating the main window
    root = Tk()
    root.title('Simple Calculator')

    # Entry widgets
    entry1 = Entry(root, width=30, borderwidth=5)
    entry1.grid(row=0, column=0, padx=10, pady=10)
    entry2 = Entry(root, width=30, borderwidth=5)
    entry2.grid(row=1, column=0, padx=10, pady=10)

    # Buttons
    button_add = Button(root, text='Add', padx=20, pady=10, command=add)
    button_add.grid(row=0, column=1, padx=10, pady=10)
    button_subtract = Button(root, text='Subtract', padx=20, pady=10, command=subtract)
    button_subtract.grid(row=1, column=1, padx=10, pady=10)
    button_multiply = Button(root, text='Multiply', padx=20, pady=10, command=multiply)
    button_multiply.grid(row=2, column=1, padx=10, pady=10)
    button_divide = Button(root, text='Divide', padx=20, pady=10, command=divide)
    button_divide.grid(row=3, column=1, padx=10, pady=10)

    # Clear button
    button_clear = Button(root, text='Clear', padx=20, pady=10, command=clear_entry)
    button_clear.grid(row=2, column=0, padx=10, pady=10)

    # Exit button
    button_exit = Button(root, text='Exit', padx=20, pady=10, command=root.quit)
    button_exit.grid(row=3, column=0, padx=10, pady=10)

    # Running the application
    root.mainloop()