import pygame

class AudioPlayer:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((800, 600))

    def play_audio(self, audio_file):
        pygame.mixer.music.load(audio_file)
        pygame.mixer.music.play()

    def run(self):
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()

            self.screen.fill((0, 0, 0))
            pygame.display.update()

if __name__ == '__main__':
    audio_player = AudioPlayer()
    audio_player.run()