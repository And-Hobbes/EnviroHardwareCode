# Add "source /home/cal/Pimoroni/auto_venv.sh" to your ~/.bashrc to activate
# the Pimoroni virtual environment automagically!
VENV_DIR="/home/cal/.virtualenvs/pimoroni"
if [ ! -f $VENV_DIR/bin/activate ]; then
  printf "Creating user Python environment in $VENV_DIR, please wait...\n"
  mkdir -p $VENV_DIR
  python3 -m venv --system-site-packages $VENV_DIR
fi
printf " ↓ ↓ ↓ ↓   Hello, we've activated a Python venv for you. To exit, type \"deactivate\".\n"
source $VENV_DIR/bin/activate
