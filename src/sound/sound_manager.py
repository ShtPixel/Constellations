"""Simple sound manager with manifest support.

Usage:
	from sound.sound_manager import SoundManager
	sm = SoundManager()
	sm.play_death()

It will try to read the sound path from assets/assets.manifest.json under
"sounds.death". If not found, falls back to assets/sounds/death.wav. If the
file or pygame mixer is unavailable, it fails silently.
"""
import os

try:
	import pygame
except Exception:
	pygame = None

try:
    # when run as module
    from src.core.assets import AssetManifest
except ModuleNotFoundError:
    try:
        from core.assets import AssetManifest
    except ModuleNotFoundError:
        AssetManifest = None  # type: ignore


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
		# Manifest lookup
		manifest_path = None
		if AssetManifest is not None:
			try:
				m = AssetManifest()
				manifest_path = m.get_sound("death")
			except Exception:
				manifest_path = None
		# Fallback path
		if not manifest_path:
			base = os.path.join(os.getcwd(), 'assets', 'sounds')
			manifest_path = os.path.join(base, 'death.wav')
		self.death_path = manifest_path
		self._death_sound = None
		if self.enabled and self.death_path and os.path.exists(self.death_path):
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
