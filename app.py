import sys
import os
import vlc
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QFileDialog, QVBoxLayout
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtCore import Qt, QUrl, QObject, pyqtSlot, pyqtSignal, QTimer, QFile, QIODevice

def ensure_qwebchannel():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    js_path = os.path.join(current_dir, "qwebchannel.js")
    if not os.path.exists(js_path):
        qfile = QFile(":/qtwebchannel/qwebchannel.js")
        if qfile.open(QIODevice.OpenModeFlag.ReadOnly):
            with open(js_path, "wb") as f:
                f.write(qfile.readAll().data())
            qfile.close()

class VideoBackend(QObject):
    time_updated = pyqtSignal(int, int) 
    state_changed = pyqtSignal(bool)    
    files_selected = pyqtSignal(list)   
    tracks_populated = pyqtSignal(list, list) 
    
    def __init__(self, player, parent=None):
        super().__init__(parent)
        self.player = player
        
    @pyqtSlot()
    def openFileDialog(self):
        filenames, _ = QFileDialog.getOpenFileNames(self.player, "Open Video", "", "Video (*.mp4 *.mkv *.avi *.mov);;All (*)")
        if filenames:
            self.files_selected.emit(filenames)

    @pyqtSlot()
    def openSubtitleDialog(self):
        filename, _ = QFileDialog.getOpenFileName(self.player, "Open Subtitle", "", "Subtitles (*.srt *.vtt *.ass);;All (*)")
        if filename:
            self.player.media_player.video_set_subtitle_file(filename)
            self.player.tracks_pushed = False 

    @pyqtSlot(str)
    def playFile(self, path):
        media = self.player.instance.media_new(path)
        self.player.media_player.set_media(media)
        self.player.media_player.play()
        self.player.tracks_pushed = False
        self.state_changed.emit(True)
        
    @pyqtSlot()
    def togglePlay(self):
        if self.player.media_player.is_playing():
            self.player.media_player.pause()
            self.state_changed.emit(False)
        else:
            self.player.media_player.play()
            self.state_changed.emit(True)

    @pyqtSlot(float)
    def seek(self, percentage):
        length = self.player.media_player.get_length()
        if length > 0:
            self.player.media_player.set_time(int(length * percentage))
            
    @pyqtSlot(float)
    def changeVolume(self, delta):
        vol = max(0, min(100, self.player.media_player.audio_get_volume() + int(delta * 100)))
        self.player.media_player.audio_set_volume(vol)
        return vol

    @pyqtSlot(int)
    def setAudioTrack(self, track_id):
        self.player.media_player.audio_set_track(track_id)
        
    @pyqtSlot(int)
    def setSubtitleTrack(self, track_id):
        self.player.media_player.video_set_spu(track_id)
        
    @pyqtSlot()
    def toggleFullscreen(self):
        if self.player.isFullScreen():
            self.player.showNormal()
        else:
            self.player.showFullScreen()

class UIOverlay(QWidget):
    def __init__(self, parent):
        # Creates a frameless, transparent window that floats on top of the main window
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        
        self.web_view = QWebEngineView(self)
        settings = self.web_view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        
        # Make the Chromium renderer transparent
        self.web_view.page().setBackgroundColor(Qt.GlobalColor.transparent)
        self.web_view.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.web_view)

class VideoPlayer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MX Player - Desktop Edition")
        self.setGeometry(100, 100, 1280, 720)
        
        # The Main Window holds ONLY the VLC Video (Opaque)
        self.video_frame = QWidget()
        self.video_frame.setStyleSheet("background-color: black;")
        self.setCentralWidget(self.video_frame)
        
        self.instance = vlc.Instance("--no-xlib --drop-late-frames")
        self.media_player = self.instance.media_player_new()
        self.tracks_pushed = False
        
        if sys.platform.startswith('linux'):
            self.media_player.set_xwindow(self.video_frame.winId())
        elif sys.platform == "win32":
            self.media_player.set_hwnd(self.video_frame.winId())
        elif sys.platform == "darwin":
            self.media_player.set_nsobject(int(self.video_frame.winId()))

        # Initialize the Floating UI Overlay
        self.overlay = UIOverlay(self)
        
        self.channel = QWebChannel()
        self.backend = VideoBackend(self)
        self.channel.registerObject("backend", self.backend)
        self.overlay.web_view.page().setWebChannel(self.channel)
        
        current_dir = os.path.dirname(os.path.abspath(__file__))
        html_path = os.path.join(current_dir, "index.html")
        self.overlay.web_view.setUrl(QUrl.fromLocalFile(html_path))
        
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.sync_with_frontend)
        self.timer.start()

    def sync_overlay(self):
        # Keeps the invisible Web UI perfectly aligned over the VLC video
        if hasattr(self, 'overlay') and self.isVisible():
            pos = self.video_frame.mapToGlobal(self.video_frame.rect().topLeft())
            self.overlay.setGeometry(pos.x(), pos.y(), self.video_frame.width(), self.video_frame.height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.sync_overlay()

    def moveEvent(self, event):
        super().moveEvent(event)
        self.sync_overlay()

    def showEvent(self, event):
        super().showEvent(event)
        self.overlay.show()
        self.sync_overlay()
        
    def closeEvent(self, event):
        self.media_player.stop()
        self.overlay.close()
        super().closeEvent(event)

    def sync_with_frontend(self):
        state = self.media_player.get_state()
        if state in [vlc.State.Playing, vlc.State.Paused]:
            curr = self.media_player.get_time()
            total = self.media_player.get_length()
            
            self.backend.time_updated.emit(curr, total)
            
            if not self.tracks_pushed and total > 0:
                audio = [{"id": t[0], "name": t[1].decode('utf-8')} for t in self.media_player.audio_get_track_description()]
                subs = [{"id": t[0], "name": t[1].decode('utf-8')} for t in self.media_player.video_get_spu_description() if t[0] != -1]
                self.backend.tracks_populated.emit(audio, subs)
                self.tracks_pushed = True

if __name__ == '__main__':
    ensure_qwebchannel()
    # Notice we REMOVED --disable-gpu! GPU acceleration is back on for smooth hover effects.
    app = QApplication(sys.argv)
    player = VideoPlayer()
    player.show()
    sys.exit(app.exec())