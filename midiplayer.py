#!/usr/bin/env python3

import sys, git, threading, time, os, fluidsynth, st7789, rtmidi
from gpiozero import Button, DigitalOutputDevice
from PIL import Image, ImageDraw, ImageFont

MESSAGE = ""
directory = '/home/pi'
file_extension = '.mid'
soundfontname = "/usr/share/sounds/sf2/General_MIDI_64_1.6.sf2"

button1 = Button(5)
button2 = Button(6)
button3 = Button(16)
button4 = Button(24)

fs = fluidsynth.Synth()
fs.start(driver="alsa")
sfid = fs.sfload(soundfontname)

pathes = ["MIDI KEYBOARD", "SOUND FONT", "MIDI FILE"]
files = ["MIDI KEYBOARD", "SOUND FONT", "MIDI FILE"]
selectedindex = 0

repo_path = os.path.dirname(os.path.abspath(__file__))
display_type = "square"

midiin = rtmidi.MidiIn()
input_ports = midiin.get_ports()
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
            origin.pull()
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

def midi_listener():
    global fs
    midiin = rtmidi.MidiIn()
    input_ports = midiin.get_ports()
    if not input_ports:
        print("No MIDI input ports found.")
        return
    midiin.open_port(len(input_ports) - 1)
    while True:
        msg = midiin.get_message()
        if msg:
            message, delta_time = msg
            status = message[0] & 0xF0
            channel = message[0] & 0x0F
            if status == 0x90 and message[2] > 0:
                fs.noteon(channel, message[1], message[2])
            elif status == 0x80 or (status == 0x90 and message[2] == 0):
                fs.noteoff(channel, message[1])
            elif status == 0xB0:
                fs.cc(channel, message[1], message[2])
            elif status == 0xC0:
                fs.program_change(channel, message[1])
            elif status == 0xE0:
                pitch = (message[2] << 7) + message[1] - 8192
                fs.pitch_bend(channel, pitch)

def resetsynth():
    global selectedindex, files, pathes, fs, operation_mode, previous_operation_mode, soundfontname
    operation_mode = "main screen"
    pathes = ["MIDI KEYBOARD", "SOUND FONT", "MIDI FILE"]
    files = ["MIDI KEYBOARD", "SOUND FONT", "MIDI FILE"]
    selectedindex = 0
    fs.delete()
    fs = fluidsynth.Synth()
    fs.start(driver="alsa")
    sfid = fs.sfload(soundfontname)

def handle_button(bt):
    global selectedindex, files, pathes, fs, operation_mode, previous_operation_mode, soundfontname
    if str(bt.pin) == "GPIO16":
        selectedindex -= 1
    if str(bt.pin) == "GPIO24":
        selectedindex += 1
    selectedindex = max(0, min(selectedindex, len(files) - 1))
    if str(bt.pin) == "GPIO6":
        resetsynth()
    if str(bt.pin) == "GPIO5":
        if operation_mode == "main screen":
            pathes = ["MIDI KEYBOARD", "SOUND FONT", "MIDI FILE"]
            files = ["MIDI KEYBOARD", "SOUND FONT", "MIDI FILE"]
            operation_mode = pathes[selectedindex]
        if operation_mode == "MIDI KEYBOARD":
            pathes = []
            files = []
            midiin = rtmidi.MidiIn()
            input_ports = midiin.get_ports()
            for port in input_ports:
                pathes.append(port)
                files.append(port)
            if previous_operation_mode == operation_mode:
                sfid = fs.sfload(soundfontname)
                try:
                    select_first_preset(fs, sfid)
                except ValueError as e:
                    print(e)
                fs.set_reverb(0.9, 0.5, 0.8, 0.7)
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
                sfid = fs.sfload(soundfontname)
                fs.play_midi_file(pathes[selectedindex])
            previous_operation_mode = operation_mode

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

while True:
    time.sleep(0.1)
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