#!/bin/bash

# A script to move a .pem key from the Windows filesystem (/mnt/c/...)
# into the WSL home directory and set the correct permissions (400).

# --- Validation ---
# Check if a file path was provided as an argument.
if [ "$#" -ne 1 ]; then
    echo "❌ Error: You must provide the path to your .pem file."
    echo "Usage: ./fix-pem.sh /mnt/c/path/to/your/key.pem"
    exit 1
fi

# The full path to the .pem file on the Windows mount.
WINDOWS_PEM_PATH="$1"

# Check if the provided file actually exists.
if [ ! -f "$WINDOWS_PEM_PATH" ]; then
    echo "❌ Error: File not found at '$WINDOWS_PEM_PATH'"
    exit 1
fi

# --- Main Logic ---
# Get just the filename from the full path (e.g., "my-key.pem").
PEM_FILENAME=$(basename "$WINDOWS_PEM_PATH")

# Define the destination path inside WSL's ~/.ssh directory.
WSL_DEST_PATH="$HOME/.ssh/$PEM_FILENAME"

echo "🔑 Starting the key fix process..."

# 1. Create the ~/.ssh directory if it doesn't exist.
mkdir -p "$HOME/.ssh"
echo "   -> Ensured ~/.ssh directory exists."

# 2. Copy the key from the Windows path to the WSL path.
cp "$WINDOWS_PEM_PATH" "$WSL_DEST_PATH"
echo "   -> Copied '$PEM_FILENAME' to ~/.ssh/"

# 3. Set the permissions to be read-only by the owner (400).
chmod 400 "$WSL_DEST_PATH"
echo "   -> Set permissions to 400 (read-only)."

# --- Completion ---
echo ""
echo "✅ Success! Your key is now secure and ready to use."
echo "New Path: $WSL_DEST_PATH"
echo ""
echo "You can now connect using a command like:"
echo "ssh -i $WSL_DEST_PATH user@your-ec2-instance.com"