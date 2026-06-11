import unittest
from src.main import main_function
from src.calculations.addition import add
from src.calculations.subtraction import subtract
from src.gui.display import display

class TestMainFunction(unittest.TestCase):
    def test_add(self):
        result = add(1, 2)
        self.assertEqual(result, 3)

    def test_subtract(self):
        result = subtract(5, 3)
        self.assertEqual(result, 2)

def main():
    display(main_function())