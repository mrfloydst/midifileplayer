#!/usr/bin/env python3

import sys, git, threading, time, os, fluidsynth, st7789, rtmidi, subprocess, select
from gpiozero import Button, DigitalOutputDevice
from PIL import Image, ImageDraw, ImageFont

MESSAGE = ""
directory = os.path.expanduser("~")
if(directory=="/root"):
    directory="/home/pi"

file_extension = '.mid'
soundfontname = "/usr/share/sounds/sf2/General_MIDI_64_1.6.sf2"

button1 = Button(5)
button2 = Button(6)
button3 = Button(16)
button4 = Button(24)

fs = fluidsynth.Synth()
fs.start(driver="alsa")
sfid = fs.sfload(soundfontname,True)

pathes = ["MIDI KEYBOARD", "SOUND FONT", "MIDI FILE", "BLUETOOTH"]
files = ["MIDI KEYBOARD", "SOUND FONT", "MIDI FILE", "BLUETOOTH"]
selectedindex = 0
use_bluetooth = 0

repo_path = os.path.dirname(os.path.abspath(__file__))
display_type = "square"

midiin = rtmidi.MidiIn()
input_ports = midiin.get_ports()
for i, port in enumerate(input_ports):
    print(f"{i}: {port}")
midi_input_index = len(input_ports) - 1
print(f"Using MIDI input: {input_ports[midi_input_index]}")

operation_mode = "main screen"
previous_operation_mode = "main_screen"

def check_for_updates(repo_path):
    try:
        repo = git.Repo(repo_path)
        origin = repo.remotes.origin
        origin.fetch()
        local_commit = repo.head.object.hexsha
        remote_commit = origin.refs[repo.active_branch.name].object.hexsha
        if local_commit != remote_commit:
            print("New updates detected! Pulling latest changes...")
            remote_ref = origin.refs[repo.active_branch.name]
            repo.head.reset(commit=remote_ref.commit, index=True, working_tree=True)
            return True
        print("No updates found. Running the script as usual.")
        return False
    except Exception as e:
        print("Error checking for updates:", e)
        return False

def select_first_preset(synth, sfid):
    for bank in range(128):
        for preset in range(128):
            if synth.program_select(0, sfid, bank, preset):
                print(f"Selected Bank {bank}, Preset {preset}")
                return
    raise ValueError("No presets found in the SoundFont")

def init_buttons():
    button1.when_pressed = handle_button
    button2.when_pressed = handle_button
    button3.when_pressed = handle_button
    button4.when_pressed = handle_button

def midi_callback(message_data, timestamp):
    message, _ = message_data
    status = message[0] & 0xF0
    channel = message[0] & 0x0F
    
    #print(f"Raw MIDI: {[hex(b) for b in message]}")
    
    if status == 0xC0 and len(message) == 2:  # Program Change
        program = message[1]
        #print(f"Program change to {program} on channel {channel}")
        fs.program_change(channel, program)
    
    note = message[1]
    velocity = message[2]
   
    #print(f"status: {status} channel: {channel}, note: {note}, velocity: {velocity}")

    if status == 0x90:  # note_on
        if velocity > 0:
            fs.noteon(channel, note, velocity)
        else:
            fs.noteoff(channel, note)  # velocity 0 = note_off
    elif status == 0x80:  # note_off
        fs.noteoff(channel, note)
    elif status == 0xB0:  # control_change
        fs.cc(channel, note, velocity)
    elif status == 0xE0:  # pitchwheel
        pitch = (velocity << 7) + note - 8192
        fs.pitch_bend(channel, pitch)

def midi_listener():
    midiin = rtmidi.MidiIn()
    ports = midiin.get_ports()
    if not ports:
        print("No MIDI input ports found.")
        return
    midiin.open_port(len(ports) - 1)
    midiin.set_callback(midi_callback)
    while True:
        time.sleep(1)  # Keep thread alive

import subprocess, time, select, sys

def _scan_live_advertising(scan_time=8):
    """
    Return dict MAC->Name for devices that advertise during the live scan window.
    Only captures NEW/CHG events seen in real time (no cache).
    """
    proc = subprocess.Popen(
        ["bluetoothctl"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    # start scanning
    proc.stdin.write("scan on\n")
    proc.stdin.flush()

    advertising = {}
    start = time.time()
    poller = select.poll()
    poller.register(proc.stdout, select.POLLIN)

    while time.time() - start < scan_time:
        events = poller.poll(200)  # 200ms
        for _fd, _ev in events:
            line = proc.stdout.readline()
            if not line:
                continue
            # bluetoothctl formats to catch:
            # [NEW] Device MAC NAME
            # [CHG] Device MAC RSSI: ...
            # Device MAC NAME   (some builds)
            line = line.strip()
            if "Device" in line:
                parts = line.split()
                # find MAC (XX:XX:XX:XX:XX:XX) and optional name after it
                mac = next((p for p in parts if ":" in p and len(p) == 17), None)
                if mac:
                    # name is everything after MAC on the line (if present)
                    idx = line.find(mac)
                    name = line[idx + len(mac):].strip()
                    if name.startswith("RSSI"):  # no name on CHG RSSI-only lines
                        name = advertising.get(mac, "")
                    advertising[mac] = name or advertising.get(mac, "")

    # stop scanning and exit
    try:
        proc.stdin.write("scan off\n")
        proc.stdin.flush()
    except Exception:
        pass
    proc.stdin.write("exit\n")
    proc.stdin.flush()
    proc.wait(timeout=2)

    return advertising

def _paired_connected_now():
    """
    Return dict MAC->Name for paired devices that are currently Connected: yes.
    """
    connected = {}
    # list paired devices
    pd = subprocess.run(["bluetoothctl", "paired-devices"], capture_output=True, text=True)
    for line in pd.stdout.splitlines():
        # Format: Device MAC NAME
        if line.startswith("Device "):
            parts = line.split(" ", 2)
            if len(parts) >= 3:
                mac, name = parts[1], parts[2]
                info = subprocess.run(["bluetoothctl", "info", mac], capture_output=True, text=True)
                if "Connected: yes" in info.stdout:
                    connected[mac] = name
    return connected

def get_online_devices(scan_time=8):
    global use_bluetooth
    result = []
    if use_bluetooth==1:
        """
        Return a list of [name, mac] for devices that are online:
        - Currently advertising (seen during live scan), OR
        - Currently connected (paired devices with Connected: yes)
        """
        adv = _scan_live_advertising(scan_time)
        con = _paired_connected_now()

        # Union: prefer names from 'adv' when available, else from 'con'
        macs = set(adv.keys()) | set(con.keys())
        for mac in macs:
            name = adv.get(mac) or con.get(mac) or ""
            # Trim leading punctuation if any
            name = name.strip()
            result.append([name, mac])
    return result

def btctl(cmds, timeout=15):
    """Run a series of bluetoothctl commands in one session, return combined stdout."""
    proc = subprocess.Popen(
        ["bluetoothctl"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, bufsize=1
    )
    for c in cmds:
        proc.stdin.write(c + "\n")
        proc.stdin.flush()
        time.sleep(0.3)
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        out = ""
    return out

def connect_ble_device(mac):
    global use_bluetooth
    if use_bluetooth==1:
        print("Connecting to ${mac}")
        btctl(["power on", "pairable on", "agent on", "default-agent"])
        btctl([f"remove {mac}"])  # clear stale record

        # make sure device object exists
        btctl(["scan on"])
        time.sleep(5)
        btctl(["scan off"])

        # try pairing
        out = btctl([f"pair {mac}"])
        if "not available" in out.lower():
            time.sleep(3)
            btctl(["scan on"]); time.sleep(5); btctl(["scan off"])
            out = btctl([f"pair {mac}"])

        # trust + connect
        btctl([f"trust {mac}"])
        out = btctl([f"connect {mac}"])
        if "Connection successful" in out or "Connected: yes" in out:
            print(f"Connected to {mac}")
            return True

        raise RuntimeError(f"Connect failed for {mac}: {out.strip()}")

def resetsynth():
    global selectedindex, files, pathes, fs, operation_mode, previous_operation_mode, soundfontname
    operation_mode = "main screen"
    pathes = ["MIDI KEYBOARD", "SOUND FONT", "MIDI FILE", "BLUETOOTH"]
    files = ["MIDI KEYBOARD", "SOUND FONT", "MIDI FILE", "BLUETOOTH"]
    selectedindex = 0
    fs.delete()
    fs = fluidsynth.Synth()
    fs.start(driver="alsa")
    sfid = fs.sfload(soundfontname,True)

def remove_all_devices():
    global use_bluetooth
    macs = []
    if use_bluetooth==1:
        print("Removing all BLE Devices")
        """Remove all registered Bluetooth devices from the controller."""
        # Get list of paired devices
        result = subprocess.run(
            ["bluetoothctl", "devices"],
            capture_output=True, text=True
        )
        for line in result.stdout.splitlines():
            if line.startswith("Device "):
                parts = line.split(" ", 2)
                if len(parts) >= 2:
                    macs.append(parts[1])

        # Remove each device
        for mac in macs:
            print(f"Removing {mac}")
            subprocess.run(["bluetoothctl", "remove", mac])

    return macs

def wait_for_midi_port(port_name_substring, timeout=10):
    global use_bluetooth
    if use_bluetooth==1:
        print("Wating for MIDI Port")
        """
        Wait until a MIDI port containing `port_name_substring` appears.
        Returns the full port name or None if timeout expires.
        """
        midi_in = rtmidi.MidiIn()
        start = time.time()
        while time.time() - start < timeout:
            ports = midi_in.get_ports()
            for p in ports:
                if port_name_substring.lower() in p.lower():
                    return p
            time.sleep(0.5)  # wait a bit before retrying
        return None

def index_of_substring(lst, substring):
    for i, val in enumerate(lst):
        if substring in val:
            return i
    return -1  # return -1 if not found, like JS indexOf

def handle_button(bt):
    global selectedindex, files, pathes, fs, operation_mode, previous_operation_mode, soundfontname, draw, disp, use_bluetooth
    if str(bt.pin) == "GPIO16":
        selectedindex -= 1
    if str(bt.pin) == "GPIO24":
        selectedindex += 1
    selectedindex = max(0, min(selectedindex, len(files) - 1))
    if str(bt.pin) == "GPIO6":
        resetsynth()
    if str(bt.pin) == "GPIO5":
        if operation_mode == "main screen":
            pathes = ["MIDI KEYBOARD", "SOUND FONT", "MIDI FILE", "BLUETOOTH"]
            files = ["MIDI KEYBOARD", "SOUND FONT", "MIDI FILE", "BLUETOOTH"]
            operation_mode = pathes[selectedindex]
        if operation_mode == "BLUETOOTH":
            if previous_operation_mode == operation_mode:
                operation_mode="main screen"
                use_bluetooth=selectedindex
            else:
                selectedindex=use_bluetooth
                pathes=["OFF","ON"]
                files=["OFF","ON"]
            previous_operation_mode = operation_mode
        if operation_mode == "MIDI KEYBOARD":
            midiin = rtmidi.MidiIn()
            if previous_operation_mode == operation_mode:
                if(files[selectedindex]!=pathes[selectedindex]):
                    draw.rectangle([10, 10 + (2 * 30), 230, 40 + (2 * 30)], fill=(235, 235, 235))
                    draw.text((10, 10 + (2 * 30)), "Please Wait", font=font, fill=(255, 0, 0))
                    disp.display(img)
                    remove_all_devices()
                    print(pathes[selectedindex])
                    print(files[selectedindex])
                    connect_ble_device(pathes[selectedindex])
                    wait_for_midi_port(files[selectedindex])
                    selectedindex = index_of_substring(midiin.get_ports(), files[selectedindex])
                if midiin.is_port_open():
                    midiin.close_port()
                midiin.open_port(selectedindex)
                midiin.set_callback(midi_callback)
                sfid = fs.sfload(soundfontname,True)
                try:
                    select_first_preset(fs, sfid)
                except ValueError as e:
                    print(e)
                fs.set_reverb(0.9, 0.5, 0.8, 0.7)
            else:
                pathes = []
                files = []
                input_ports = midiin.get_ports()
                for port in input_ports:
                    pathes.append(port)
                    files.append(port)
                # scan for new BT devices only once
                draw.rectangle([10, 10 + (2 * 30), 230, 40 + (2 * 30)], fill=(235, 235, 235))
                draw.text((10, 10 + (2 * 30)), "Please Wait", font=font, fill=(255, 0, 0))
                disp.display(img)
                remove_all_devices()
                for mac,name in get_online_devices(7):
                    pathes.append(name)
                    files.append(mac)
            previous_operation_mode = operation_mode
        if operation_mode == "SOUND FONT":
            pathes = []
            files = []
            target_directory = os.readlink(directory + "/sf2")
            for dirpath, dirnames, filenames in os.walk(target_directory):
                for filename in filenames:
                    if filename.endswith(".sf2"):
                        pathes.append(dirpath + "/" + filename)
                        files.append(filename.replace(".sf2", "").replace("_", " "))
            if previous_operation_mode == operation_mode:
                soundfontname = pathes[selectedindex]
                resetsynth()
            previous_operation_mode = operation_mode
        if operation_mode == "MIDI FILE":
            pathes = []
            files = []
            for dirpath, dirnames, filenames in os.walk(directory + "/midifiles"):
                for filename in filenames:
                    if filename.endswith(file_extension):
                        pathes.append(dirpath + "/" + filename)
                        files.append(filename.replace(".mid", "").replace("_", " "))
            if previous_operation_mode == operation_mode:
                operation_mode = "main screen"
                fs.delete()
                fs = fluidsynth.Synth()
                fs.start(driver="alsa")
                sfid = fs.sfload(soundfontname,True)
                fs.play_midi_file(pathes[selectedindex])
            previous_operation_mode = operation_mode
    update_display()

def update_display():
    draw.rectangle((0, 0, disp.width, disp.height), (0, 0, 0))
    for i, line in enumerate(files):
        if i >= selectedindex - 6:
            xi = i
            if selectedindex > 6:
                xi = i - (selectedindex - 6)
            if i == selectedindex:
                draw.rectangle([10, 10 + (xi * 30), 230, 40 + (xi * 30)], fill=(255, 255, 255))
                draw.text((10, 10 + (xi * 30)), line, font=font, fill=(0, 0, 0))
            else:
                draw.text((10, 10 + (xi * 30)), line, font=font, fill=(255, 255, 255))
    disp.display(img)

if check_for_updates(repo_path):
    print("Restarting script to apply updates...")
    os.execv(sys.executable, ['python'] + sys.argv)

gpio_thread = threading.Thread(target=init_buttons)
gpio_thread.start()

midi_thread = threading.Thread(target=midi_listener)
midi_thread.start()

if display_type in ("square", "rect", "round"):
    disp = st7789.ST7789(
        height=135 if display_type == "rect" else 240,
        rotation=0 if display_type == "rect" else 90,
        port=0,
        cs=st7789.BG_SPI_CS_FRONT,
        dc=9,
        backlight=13,
        spi_speed_hz=80 * 1000 * 1000,
        offset_left=0 if display_type == "square" else 40,
        offset_top=53 if display_type == "rect" else 0,
    )
elif display_type == "dhmini":
    disp = st7789.ST7789(
        height=240,
        width=320,
        rotation=180,
        port=0,
        cs=1,
        dc=9,
        backlight=13,
        spi_speed_hz=60 * 1000 * 1000,
        offset_left=0,
        offset_top=0,
    )
else:
    print("Invalid display type!")

disp.begin()
WIDTH = disp.width
HEIGHT = disp.height
img = Image.new("RGB", (WIDTH, HEIGHT), color=(0, 0, 0))
draw = ImageDraw.Draw(img)
font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)

# remove all known bluetooth devices...
remove_all_devices()

update_display()

# Keep the script alive
while True:
    time.sleep(10)
