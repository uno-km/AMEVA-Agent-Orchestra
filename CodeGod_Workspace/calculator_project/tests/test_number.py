import unittest

class TestNumber(unittest.TestCase):
    def test_add(self):
        self.assertEqual(1 + 2, 3)

    def test_subtract(self):
        self.assertEqual(5 - 3, 2)

    def test_multiply(self):
        self.assertEqual(4 * 2, 8)

    def test_divide(self):
        self.assertEqual(8 / 2, 4)