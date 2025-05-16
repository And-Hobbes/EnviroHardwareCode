printf "It's recommended you run these steps manually.\n"
printf "If you want to run the full script, open it in\n"
printf "an editor and remove 'exit 1' from below.\n"
exit 1
source /home/cal/.virtualenvs/pimoroni/bin/activate
python -m pip uninstall enviroplus
cp /home/cal/Pimoroni/config-backups/config.preinstall-enviroplus-2024-10-15-16-01-26.txt /boot/firmware/config.txt
