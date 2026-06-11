from tkinter import Button

class MyButton(Button):
    def __init__(self, master=None, **kwargs):
        super().__init__(master=master, **kwargs)
        self.text = 'Click Me'
        self.pack(pady=10)