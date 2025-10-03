#!/bin/bash

# This script installs Docker and Docker Compose on an Ubuntu 22.04 system.

# Exit immediately if a command exits with a non-zero status.
set -e

echo "🚀 Starting Docker installation..."

# 1. UPDATE SYSTEM AND INSTALL PREREQUISITES
echo "### Step 1: Updating package index and installing prerequisites... ###"
sudo apt-get update
sudo apt-get install -y \
    ca-certificates \
    curl \
    gnupg

# 2. ADD DOCKER'S OFFICIAL GPG KEY
echo "### Step 2: Adding Docker's official GPG key... ###"
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# 3. SET UP THE DOCKER REPOSITORY
echo "### Step 3: Setting up the Docker repository... ###"
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# 4. INSTALL DOCKER ENGINE
echo "### Step 4: Installing Docker Engine... ###"
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 5. ADD USER TO THE DOCKER GROUP (to run docker commands without sudo)
echo "### Step 5: Adding current user to the 'docker' group... ###"
sudo usermod -aG docker $USER

# 6. ENABLE AND START DOCKER SERVICE
echo "### Step 6: Enabling and starting the Docker service... ###"
sudo systemctl enable docker.service
sudo systemctl start docker.service

echo "✅ Docker has been installed successfully!"
echo "➡️ IMPORTANT: You must log out and log back in for the group changes to take effect."
echo "After logging back in, you can verify the installation by running: docker run hello-world"