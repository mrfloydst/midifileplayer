# midifileplayer
Plays back midi files on a Raspberry PI and lets you play sounds on a MIDI keyboard

How to install/use  
Install 32 bit os lite, bookworm or bullseye

ssh to raspberrypi  
mkdir midifiles   # put your midifiles into this folder  
sudo apt update  
sudo apt upgrade  
sudo apt install fluidsynth bluez alsa-utils
sudo raspi-config  # turn on spi and i2c  

sudo nano /boot/firmware/config.txt, add  
dtoverlay=hifiberry-dac  
gpio=25=op,dh

sudo apt-get install git python3-rpi.gpio python3-spidev python3-pip python3-pil python3-numpy
sudo pip3 install pidi-display-st7789 --break-system-packages  
sudo pip3 install gitpython --break-system-packages  
sudo pip3 install pyfluidsynth --break-system-packages  
sudo pip3 install python-rtmidi --break-system-packages    
sudo pip3 install python-rtmidi --break-system-packages  
sudo python3 -m pip install mido --break-system-packages  
git clone  https://github.com/pimoroni/st7789-python  
cd st7789-python/examples/  
sudo apt install libopenblas-dev  

Test if the display is working:  
python3 scrolling-text.py  
should display a scrolling text.  

Edit "limits.conf" and add two lines as follows:

sudo nano /etc/security/limits.conf  
@audio - rtprio 90  
@audio - memlock unlimited  

Reboot the system:  
sudo reboot

After logging back in:  
cd ~  
git clone https://github.com/mrfloydst/midifileplayer  
ln -s /usr/share/sounds/sf2 .  

cd /usr/share/sounds/sf2  
sudo wget http://ntonyx.com/soft/32MbGMStereo.sf2  
sudo wget https://musical-artifacts.com/artifacts/923/General_MIDI_64_1.6.sf2  

To make the script autostart:  
export EDITOR=nano  
crontab -e

THEN, in the last line, add

@reboot sudo /usr/bin/python3 /home/pi/midifileplayer/midiplayer.py > /home/pi/mlog.txt

You must create a subdirectory named "midifiles" in /home/pi that will contain the .mid files. The Python code fails if this directory does not exist. (The README mentions creating this directory, but not that it is required)
You have to create a symbolic link named "sf2" in /home/pi linked to where the .sf2 files are stored (probably /usr/share/sounds/sf2) or the Python code will fail.

there's an SD card image for RasPi Zero 2 here:  
https://1drv.ms/u/c/5cc3ff9db18d3aed/EeThL7ORdWpCsPFlJCnd7fIBYfMfCscALHBu-Y-uZmMnvg?e=FKUpo0  

(Download any MIDI file)  
fluidsynth -a alsa -n -i /usr/share/sounds/sf2/FluidR3_GM.sf2 midifile.mid

IF YOU GET AN ERROR SAYING "THE DEFAULT AUDIO DEVICE IS USED BY ANOTHER APPLICATION", try these steps:  
When installing fluidsynth, it will be installed as a service (for whatever reason) - please do the following:  
sudo systemctl disable fluidsynth.service

if that does not help, try

sudo mv /usr/lib/systemd/user/fluidsynth.service /usr/lib/systemd/user/fluidsynth.service_nonono

Then reboot.  
If that doesn't help, try editing the /boot/firmware/config.txt file in your boot folder and change this line:  
#Enable audio (loads snd_bcm2835)  
dtparam=audio=off    # (was on)
