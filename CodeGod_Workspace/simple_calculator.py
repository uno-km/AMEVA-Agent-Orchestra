class SimpleCalculator:
    def __init__(self):
        self.result = 0

    def add(self, num1, num2):
        self.result = num1 + num2
        return self.result

if __name__ == '__main__':
    calc = SimpleCalculator()
    num1 = int(input('첫 번째 숫자를 입력하세요: '))
    num2 = int(input('두 번째 숫자를 입력하세요: '))
    print('두 숫자의 합:', calc.add(num1, num2))