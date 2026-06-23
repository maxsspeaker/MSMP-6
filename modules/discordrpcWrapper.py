import time
import traceback
import discordrpc

from .types import *

class discordrpcWrapper:
    def __init__(self,MainWindow):
        try:
            print("connecting to discordrpc")
            self.rpc = discordrpc.RPC(app_id=811577404279619634)
        except Exception:
            traceback.print_exc()
            self.rpc = None

        self.MainWindow=MainWindow
        self.Status="Stopped"

        self.itemSelected=None
        self.position=0

        try:
            if(self.rpc):
                self.rpc.set_activity(
                        state=None,
                        details=None,
                        act_type=discordrpc.Activity.Listening,
                        large_image="msmpwave",
                        small_image=self.Status.lower(),
                        small_text=self.Status,
                        large_text=None
                        )
        except:
            self.rpc = None


    def set_activity(self, item: PlaylistItem) -> None:
        self.itemSelected=item

        self.position=int(self.MainWindow.player.position()/1000)

        #print(self.itemSelected.artwork_url)

        #self.track_title_label.setText(item.title or "No track")
        #self.artist_label.setText(item.uploader or "Unknown artist")
        #self.album_label.setText(item.album or self.playlist_title or "Unknown album")
        if(self.rpc):
            if not(self.Status=="Playing"):
                ts_start=None
                ts_end=None
            else:
                ts_start=int(time.time()) - self.position
                ts_end=int(time.time()) + self.itemSelected.duration - self.position
            try:
                self.rpc.set_activity(
                    state=self.itemSelected.uploader or "Unknown artist",
                    details=self.itemSelected.title,
                    act_type=discordrpc.Activity.Listening,
                    ts_start=ts_start,
                    ts_end=ts_end,
                    large_image=self.itemSelected.artwork_url,
                    small_image=self.Status.lower(),
                    small_text=self.Status,
                    large_text=self.itemSelected.album or self.MainWindow.playlist_title or None
                    )
            except:
                traceback.print_exc()
                self.rpc = None
    def set_playback_status(self, status: str) -> None:
        if status not in {"Playing", "Paused", "Stopped"}:
            return

        self.Status=status
        self.position=int(self.MainWindow.player.position()/1000)
        print(self.position)

        if(self.rpc):
            try:
                ts_start=None
                ts_end=None
                if (self.Status=="Playing"):
                    ts_start=int(time.time()) - self.position
                    ts_end=int(time.time()) + self.itemSelected.duration - self.position
                elif(self.Status=="Stopped"):
                    self.rpc.set_activity(
                        state=None,
                        details=None,
                        act_type=discordrpc.Activity.Listening,
                        ts_start=ts_start,
                        ts_end=ts_end,
                        large_image="msmpwave",
                        small_image=self.Status.lower(),
                        small_text=self.Status,
                        large_text=None
                        )
                    return
            
                self.rpc.set_activity(
                    state=self.itemSelected.uploader or "Unknown artist",
                    details=self.itemSelected.title,
                    act_type=discordrpc.Activity.Listening,
                    ts_start=ts_start,
                    ts_end=ts_end,
                    large_image=self.itemSelected.artwork_url,
                    small_image=self.Status.lower(),
                    small_text=self.Status,
                    large_text=self.itemSelected.album or self.MainWindow.playlist_title or None
                    )
            except:
                traceback.print_exc()
                self.rpc = None
    def sync_position(self, position_ms: int) -> None:
        self.position=int(position_ms/1000)
        if(self.rpc):
            if not(self.Status=="Playing"):
                ts_start=None
                ts_end=None
            else:
                ts_start=int(time.time()) - self.position
                ts_end=int(time.time()) + self.itemSelected.duration - self.position
            try:
                self.rpc.set_activity(
                    state=self.itemSelected.uploader or "Unknown artist",
                    details=self.itemSelected.title,
                    act_type=discordrpc.Activity.Listening,
                    ts_start=ts_start,
                    ts_end=ts_end,
                    large_image=self.itemSelected.artwork_url,
                    small_image=self.Status.lower(),
                    small_text=self.Status,
                    large_text=self.itemSelected.album or self.MainWindow.playlist_title or None
                    )
            except:
                traceback.print_exc()
                self.rpc = None