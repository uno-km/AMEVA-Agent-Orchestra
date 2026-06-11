import tkinter as tk
from src.app.ui.calculator_ui import CalculatorUI

class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title('Calculator')
        self.ui = CalculatorUI(self)
        self.run()

if __name__ == '__main__':
    app = App()