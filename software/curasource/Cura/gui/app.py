__copyright__ = "Copyright (C) 2013 David Braam - Released under terms of the AGPLv3 License"

import sys
import os
import platform
import shutil
import glob
import subprocess
import warnings

try:
	#Only try to import the _core to save import time
	import wx._core
except ImportError:
	import wx


class CuraApp(wx.App):
	def __init__(self, files):
		if platform.system() == "Windows" and not 'PYCHARM_HOSTED' in os.environ:
			from Cura.util import profile
			super(CuraApp, self).__init__(redirect=True, filename=os.path.join(profile.getBasePath(), 'output_log.txt'))
		else:
			super(CuraApp, self).__init__(redirect=False)

		self.mainWindow = None
		self.splash = None
		self.loadFiles = files

		if platform.system() == "Darwin":
			self.Bind(wx.EVT_ACTIVATE_APP, self.OnActivate)

		if sys.platform.startswith('win'):
			#Check for an already running instance, if another instance is running load files in there
			from Cura.util import version
			from ctypes import windll
			import ctypes
			import socket
			import threading

			portNr = 0xCA00 + sum(map(ord, version.getVersion(False)))
			if len(files) > 0:
				try:
					other_hwnd = windll.user32.FindWindowA(None, ctypes.c_char_p('Cura - ' + version.getVersion()))
					if other_hwnd != 0:
						sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
						sock.sendto('\0'.join(files), ("127.0.0.1", portNr))

						windll.user32.SetForegroundWindow(other_hwnd)
						return
				except:
					pass

			socketListener = threading.Thread(target=self.Win32SocketListener, args=(portNr,))
			socketListener.daemon = True
			socketListener.start()

		if sys.platform.startswith('darwin'):
			#Do not show a splashscreen on OSX, as by Apple guidelines
			self.afterSplashCallback()
		else:
			from Cura.gui import splashScreen
			self.splash = splashScreen.splashScreen(self.afterSplashCallback)

	def MacOpenFile(self, path):
		try:
			self.mainWindow.OnDropFiles([path])
		except Exception as e:
			warnings.warn("File at {p} cannot be read: {e}".format(p=path, e=str(e)))

	def MacReopenApp(self, event):
		self.GetTopWindow().Raise()

	def MacHideApp(self, event):
		self.GetTopWindow().Show(False)

	def MacNewFile(self):
		pass

	def MacPrintFile(self, file_path):
		pass

	def OnActivate(self, e):
		if e.GetActive():
			self.GetTopWindow().Raise()
		e.Skip()

	def Win32SocketListener(self, port):
		import socket
		try:
			sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
			sock.bind(("127.0.0.1", port))
			while True:
				data, addr = sock.recvfrom(2048)
				try:
					wx.CallAfter(self.mainWindow.OnDropFiles, data.split('\0'))
				except Exception as e:
					warnings.warn("File at {p} cannot be read: {e}".format(p=data, e=str(e)))
		except:
			pass

	def destroySplashScreen(self):
		if self.splash is not None:
			self.splash.Show(False)
			self.splash.Destroy()
			self.splash = None

	def afterSplashCallback(self):
		#These imports take most of the time and thus should be done after showing the splashscreen
		import webbrowser
		from Cura.gui import mainWindow
		from Cura.gui import configWizard
		from Cura.gui import newVersionDialog
		from Cura.util import profile
		from Cura.util import resources
		from Cura.util import version

		# Looks like on Windows, for some reason (wx inspector?), stdout is redirected to a wx.py.pseudo.PsuedoFile object, which
		# prevents any prints/exceptions/etc.. from appearing on a console. This fixes it so we can have a normal stdout on windows.
		sys.stdout = sys.__stdout__

		resources.setupLocalization(profile.getPreference('language'))  # it's important to set up localization at very beginning to install _

		try:
			from distutils.version import LooseVersion

			if LooseVersion(wx.__version__) < LooseVersion('3.0'):
				wx.MessageBox(_("This version of Cura requires WxPython version 3.0 or newer.\nYour current WxPython version is %s.") % wx.__version__,
							  _("WxPython version is too old"), wx.OK | wx.ICON_ERROR)
				return
		except:
			# distutils not found.. it can happen!
			# Only check the first 3 characters of the version string instead
			if float(wx.__version__[0:3]) < 3.0:
				wx.MessageBox(_("This version of Cura requires WxPython version 3.0 or newer.\nYour current WxPython version is %s.") % wx.__version__,
							  _("WxPython version is too old"), wx.OK | wx.ICON_ERROR)
				return

		#If we do not have preferences yet, try to load it from a previous Cura install
		if profile.getMachineSetting('machine_type') == 'unknown':
			try:
				otherCuraInstalls = profile.getAlternativeBasePaths()
				for path in otherCuraInstalls[::-1]:
					try:
						print 'Loading old settings from %s' % (path)
						profile.loadPreferences(os.path.join(path, 'preferences.ini'))
						profile.loadProfile(os.path.join(path, 'current_profile.ini'))
						break
					except:
						import traceback
						print traceback.print_exc()
			except:
				import traceback
				print traceback.print_exc()

		#If we haven't run it before, run the configuration wizard.
		if profile.getMachineSetting('machine_type') == 'unknown':
			#Check if we need to copy our examples
			exampleFile = os.path.normpath(os.path.join(resources.resourceBasePath, 'example', 'Rocktopus.stl'))

			self.loadFiles = [exampleFile]
			self.destroySplashScreen()
			configWizard.ConfigWizard()

		if profile.getPreference('check_for_updates') == 'True':
			newVersion = version.checkForNewerVersion()
			if newVersion is not None:
				self.destroySplashScreen()
				if wx.MessageBox(_("A new version of Cura is available, would you like to download?"), _("New version available"), wx.YES_NO | wx.ICON_INFORMATION) == wx.YES:
					webbrowser.open(newVersion)
					return
		if profile.getMachineSetting('machine_name') == '':
			return
		if profile.getPreference('last_run_version') != version.getVersion(False):
			profile.performVersionUpgrade()

		# Must happen before the main window is created, in case there are changes
		# that would affect it (such as machine name changes)
		if version.isDevVersion():
			profile.performVersionUpgrade()

		self.mainWindow = mainWindow.mainWindow()
		self.destroySplashScreen()
		self.SetTopWindow(self.mainWindow)
		self.mainWindow.Show()
		self.mainWindow.OnDropFiles(self.loadFiles)
		setFullScreenCapable(self.mainWindow)

		if profile.getPreference('last_run_version') != version.getVersion(False):
			profile.putPreference('last_run_version', version.getVersion(False))
			newVersionDialog.newVersionDialog().Show()

		# Must come after creating the main window
		#if version.isDevVersion():
			#import wx.lib.inspection
			# Show the WX widget inspection tool
			#wx.lib.inspection.InspectionTool().Show()

		if sys.platform.startswith('darwin'):
			wx.CallAfter(self.StupidMacOSWorkaround)

	def StupidMacOSWorkaround(self):
		subprocess.Popen(['osascript', '-e', '''\
		tell application "System Events"
		set procName to name of first process whose unix id is %s
		end tell
		tell application procName to activate
		''' % os.getpid()])

if platform.system() == "Darwin": #Mac magic. Dragons live here. THis sets full screen options.
	try:
		import ctypes, objc
		_objc = ctypes.PyDLL(objc._objc.__file__)

		# PyObject *PyObjCObject_New(id objc_object, int flags, int retain)
		_objc.PyObjCObject_New.restype = ctypes.py_object
		_objc.PyObjCObject_New.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]

		def setFullScreenCapable(frame):
			frameobj = _objc.PyObjCObject_New(frame.GetHandle(), 0, 1)

			NSWindowCollectionBehaviorFullScreenPrimary = 1 << 7
			window = frameobj.window()
			newBehavior = window.collectionBehavior() | NSWindowCollectionBehaviorFullScreenPrimary
			window.setCollectionBehavior_(newBehavior)
	except:
		def setFullScreenCapable(frame):
			pass

else:
	def setFullScreenCapable(frame):
		pass
