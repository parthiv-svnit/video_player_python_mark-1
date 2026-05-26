import sys
import os
import vlc
import subprocess
import base64
import concurrent.futures
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QFileDialog, QVBoxLayout
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtCore import Qt, QUrl, QObject, pyqtSlot, pyqtSignal, QTimer, QFile, QIODevice, QEvent

def ensure_qwebchannel():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    js_path = os.path.join(current_dir, "qwebchannel.js")
    if not os.path.exists(js_path):
        qfile = QFile(":/qtwebchannel/qwebchannel.js")
        if qfile.open(QIODevice.OpenModeFlag.ReadOnly):
            with open(js_path, "wb") as f:
                f.write(qfile.readAll().data())
            qfile.close()

class DropFilter(QObject):
    def __init__(self, backend):
        super().__init__()
        self.backend = backend

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.DragEnter:
            if event.mimeData().hasUrls():
                event.accept()
                return True
        elif event.type() == QEvent.Type.Drop:
            if event.mimeData().hasUrls():
                paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
                if paths:
                    self.backend.files_selected.emit(paths)
                event.accept()
                return True
        return super().eventFilter(obj, event)

class VideoBackend(QObject):
    time_updated = pyqtSignal(int, int) 
    state_changed = pyqtSignal(bool)    
    files_selected = pyqtSignal(list)   
    tracks_populated = pyqtSignal(list, list, int, int) 
    video_ended = pyqtSignal()
    thumbnail_ready = pyqtSignal(float, str) 
    
    def __init__(self, player, parent=None):
        super().__init__(parent)
        self.player = player
        self.current_video_path = ""
        self.threadpool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.thumb_cache = {}
        self.last_thumb_time = -1
        
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
        self.current_video_path = path
        self.thumb_cache.clear() 
        
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

    @pyqtSlot()
    def stopPlay(self):
        self.player.media_player.stop()
        self.state_changed.emit(False)

    @pyqtSlot(float)
    def seek(self, percentage):
        percentage = max(0.0, min(1.0, percentage))
        state = self.player.media_player.get_state()
        if state == vlc.State.Ended:
            self.player.media_player.stop()
            self.player.media_player.play()
            
        length = self.player.media_player.get_length()
        if length > 0:
            self.player.media_player.set_time(int(length * percentage))
            
    @pyqtSlot(int)
    def seekRelative(self, ms):
        state = self.player.media_player.get_state()
        if state == vlc.State.Ended:
            self.player.media_player.stop()
            self.player.media_player.play()
            
        length = max(1, self.player.media_player.get_length())
        current = max(0, self.player.media_player.get_time())
        self.player.media_player.set_time(max(0, min(length, current + ms)))
        
    @pyqtSlot(int)
    def seekFrame(self, frames):
        fps = self.player.media_player.get_fps()
        if fps <= 0: fps = 30.0 
        self.seekRelative(int((1000.0 / fps) * frames))

    @pyqtSlot(result=bool)
    def toggleMute(self):
        is_muted = self.player.media_player.audio_get_mute()
        self.player.media_player.audio_set_mute(not is_muted)
        return not is_muted
        
    @pyqtSlot(float, result=int)
    def changeVolume(self, delta):
        current_vol = self.player.media_player.audio_get_volume()
        if current_vol < 0: current_vol = 100 
        vol = max(0, min(100, current_vol + int(delta * 100)))
        self.player.media_player.audio_set_volume(vol)
        return vol

    @pyqtSlot(int)
    def setAudioTrack(self, track_id):
        self.player.media_player.audio_set_track(track_id)
        
    @pyqtSlot(int)
    def setSubtitleTrack(self, track_id):
        self.player.media_player.video_set_spu(track_id)

    @pyqtSlot(float)
    def setRate(self, rate):
        self.player.media_player.set_rate(rate)

    @pyqtSlot(float)
    def requestThumbnail(self, time_sec):
        if not self.current_video_path: return
        time_sec = round(time_sec)
        self.last_thumb_time = time_sec
        
        if time_sec in self.thumb_cache:
            self.thumbnail_ready.emit(time_sec, self.thumb_cache[time_sec])
            return
            
        def extract():
            if self.last_thumb_time != time_sec: return
            cmd = [
                "ffmpeg", "-y", "-ss", str(time_sec), "-i", self.current_video_path,
                "-vframes", "1", "-q:v", "5", "-s", "160x90",
                "-f", "image2pipe", "-vcodec", "mjpeg", "-"
            ]
            try:
                kwargs = {}
                if sys.platform == "win32":
                    kwargs['creationflags'] = 0x08000000 
                
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, **kwargs)
                out, _ = p.communicate()
                
                if out and self.last_thumb_time == time_sec:
                    b64 = base64.b64encode(out).decode('utf-8')
                    data_url = f"data:image/jpeg;base64,{b64}"
                    self.thumb_cache[time_sec] = data_url
                    self.thumbnail_ready.emit(time_sec, data_url)
            except Exception:
                pass
                
        self.threadpool.submit(extract)
        
    @pyqtSlot()
    def toggleFullscreen(self):
        if self.player.isFullScreen():
            # Safely restore to exact prior state without doubling up events
            if self.player.was_maximized:
                self.player.showMaximized()
            else:
                self.player.showNormal()
        else:
            self.player.was_maximized = self.player.isMaximized()
            self.player.showFullScreen()

class UIOverlay(QWidget):
    def __init__(self, parent, backend):
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setContentsMargins(0, 0, 0, 0)
        self.setAcceptDrops(True)
        
        self.web_view = QWebEngineView(self)
        self.web_view.setContentsMargins(0, 0, 0, 0)
        self.web_view.setStyleSheet("border: none; outline: none; background: transparent;")
        
        settings = self.web_view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        
        self.web_view.page().setBackgroundColor(Qt.GlobalColor.transparent)
        self.web_view.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.web_view.setAcceptDrops(True)
        
        self.drop_filter = DropFilter(backend)
        self.web_view.installEventFilter(self.drop_filter)
        if self.web_view.focusProxy():
            self.web_view.focusProxy().installEventFilter(self.drop_filter)
            self.web_view.focusProxy().setAcceptDrops(True)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.web_view)

    def closeEvent(self, event):
        # FIX: Ensure pressing Alt+F4 on the overlay reliably shuts down the entire app
        if self.parent() and hasattr(self.parent(), 'is_closing') and not self.parent().is_closing:
            self.parent().close()
        super().closeEvent(event)

class VideoPlayer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MX Player - Desktop Edition")
        self.setGeometry(100, 100, 1280, 720)
        self.was_maximized = False
        self.is_closing = False
        
        self.setContentsMargins(0, 0, 0, 0)
        self.setStyleSheet("QMainWindow { background-color: black; border: none; margin: 0px; padding: 0px; }")
        self.setStatusBar(None)
        self.setMenuBar(None)
        
        self.video_frame = QWidget()
        self.video_frame.setContentsMargins(0, 0, 0, 0)
        self.video_frame.setStyleSheet("background-color: black; border: none; margin: 0px; padding: 0px;")
        self.setCentralWidget(self.video_frame)
        
        self.instance = vlc.Instance("--no-xlib --drop-late-frames")
        self.media_player = self.instance.media_player_new()
        self.tracks_pushed = False
        self.last_state = None 
        
        if sys.platform.startswith('linux'):
            self.media_player.set_xwindow(self.video_frame.winId())
        elif sys.platform == "win32":
            self.media_player.set_hwnd(self.video_frame.winId())
        elif sys.platform == "darwin":
            self.media_player.set_nsobject(int(self.video_frame.winId()))

        self.backend = VideoBackend(self)
        self.channel = QWebChannel()
        self.channel.registerObject("backend", self.backend)

        self.overlay = UIOverlay(self, self.backend)
        self.overlay.web_view.page().setWebChannel(self.channel)
        
        current_dir = os.path.dirname(os.path.abspath(__file__))
        html_path = os.path.join(current_dir, "index.html")
        self.overlay.web_view.setUrl(QUrl.fromLocalFile(html_path))
        
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.sync_with_frontend)
        self.timer.start()

    def sync_overlay(self):
        if hasattr(self, 'overlay') and self.isVisible():
            if self.isFullScreen():
                # FIX: Snaps exactly to hardware screen borders to destroy DWM shadow gaps
                self.overlay.setGeometry(self.screen().geometry())
            else:
                pos = self.video_frame.mapToGlobal(self.video_frame.rect().topLeft())
                self.overlay.setGeometry(pos.x(), pos.y(), self.video_frame.width(), self.video_frame.height())

    def keyPressEvent(self, event):
        # FIX: Forward all keyboard shortcuts directly to the Chromium layer safely
        if hasattr(self, 'overlay') and self.overlay.isVisible():
            QApplication.sendEvent(self.overlay.web_view.focusProxy(), event)
        super().keyPressEvent(event)

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
        self.is_closing = True
        self.media_player.stop()
        if hasattr(self, 'overlay'):
            self.overlay.close()
        super().closeEvent(event)

    def sync_with_frontend(self):
        state = self.media_player.get_state()
        
        if state == vlc.State.Ended and self.last_state != vlc.State.Ended:
            self.backend.state_changed.emit(False)
            self.backend.video_ended.emit()
        self.last_state = state
        
        if state in [vlc.State.Playing, vlc.State.Paused]:
            curr = self.media_player.get_time()
            total = self.media_player.get_length()
            
            self.backend.time_updated.emit(curr, total)
            
            if not self.tracks_pushed and total > 0:
                self.media_player.video_set_spu(-1)
                
                audio = [{"id": t[0], "name": t[1].decode('utf-8')} for t in self.media_player.audio_get_track_description()]
                subs = [{"id": t[0], "name": t[1].decode('utf-8')} for t in self.media_player.video_get_spu_description() if t[0] != -1]
                
                curr_audio = self.media_player.audio_get_track()
                curr_sub = self.media_player.video_get_spu() 
                
                self.backend.tracks_populated.emit(audio, subs, curr_audio, curr_sub)
                self.tracks_pushed = True

if __name__ == '__main__':
    ensure_qwebchannel()
    app = QApplication(sys.argv)
    player = VideoPlayer()
    player.show()
    sys.exit(app.exec())