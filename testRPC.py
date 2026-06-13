import discordrpc
from discordrpc import Activity
import time


rpc = discordrpc.RPC(app_id=813106125942947881)


current_time = int(time.time())-150
finish_time = current_time + 200

rpc.set_activity(
      state="With activity type",
      details="Music",
      act_type=Activity.Listening,
      ts_start=current_time,
      ts_end=finish_time
)

while True:
      time.sleep(1)
#rpc.run()