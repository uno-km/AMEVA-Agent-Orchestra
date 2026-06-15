#!/usr/bin/env python3
import tkinter as tk
from gui_framework import CalculatorGUI

def main():
    root = tk.Tk()
    app = CalculatorGUI(root)
    root.mainloop()

if __name__ == '__main__':
    main()