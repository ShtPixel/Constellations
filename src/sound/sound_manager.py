"""Simple sound manager placeholder.

Usage:
	from sound.sound_manager import SoundManager
	sm = SoundManager()
	sm.play_death()

Looks for assets/sounds/death.wav; if missing or pygame.mixer not init, it fails silently.
"""
import os

try:
	import pygame
except Exception:
	pygame = None


class SoundManager:
	def __init__(self):
		self.enabled = False
		if pygame is None:
			return
		try:
			if not pygame.mixer.get_init():
				pygame.mixer.init()
			self.enabled = True
		except Exception:
			self.enabled = False
		base = os.path.join(os.getcwd(), 'assets', 'sounds')
		self.death_path = os.path.join(base, 'death.wav')
		self._death_sound = None
		if self.enabled and os.path.exists(self.death_path):
			try:
				self._death_sound = pygame.mixer.Sound(self.death_path)
			except Exception:
				self._death_sound = None

	def play_death(self):
		if self.enabled and self._death_sound:
			try:
				self._death_sound.play()
			except Exception:
				pass
