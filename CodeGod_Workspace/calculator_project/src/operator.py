from math import sqrt, pow

class Operator:
    def add(self, a, b):
        return a + b

    def subtract(self, a, b):
        return a - b

    def multiply(self, a, b):
        return a * b

    def divide(self, a, b):
        if b == 0:
            return 'Error: Division by zero'
        return a / b

    def square_root(self, a):
        return sqrt(a)

    def power(self, a, b):
        return pow(a, b)