from math import sqrt

class Number:
    def __init__(self, value):
        self.value = value

    def add(self, other):
        return Number(self.value + other.value)

    def subtract(self, other):
        return Number(self.value - other.value)

    def multiply(self, other):
        return Number(self.value * other.value)

    def divide(self, other):
        if other.value == 0:
            return None
        return Number(self.value / other.value)

    def square_root(self):
        return Number(sqrt(self.value))

    def __str__(self):
        return str(self.value)