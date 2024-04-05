#!/bin/bash
echo "Build and Push jasonacox/pypowerwall to Docker Hub"
echo ""

last_path=$(basename $PWD)
if [ "$last_path" == "proxy" ]; then
  # Remove test link
  rm -rf pypowerwall
  cp -r ../pypowerwall .
  
  # Determine version
  PROXY=`grep "BUILD = " server.py | cut -d\" -f2`
  PYPOWERWALL=`echo -n "import pypowerwall
print(pypowerwall.version)" | (cd ..; python3)`
  VER="${PYPOWERWALL}${PROXY}-beta${1}"

  # Check with user before proceeding
  echo "Build and push jasonacox/pypowerwall:${VER} to Docker Hub?"
  read -p "Press [Enter] to continue or Ctrl-C to cancel..."
  
  # Build jasonacox/pypowerwall:x.y.z
  echo "* BUILD jasonacox/pypowerwall:${VER}"
  docker buildx build -f Dockerfile.beta --no-cache --platform linux/amd64,linux/arm64,linux/arm/v7 --push -t jasonacox/pypowerwall:${VER} .
  echo ""

  # Verify
  echo "* VERIFY jasonacox/pypowerwall:${VER}"
  docker buildx imagetools inspect jasonacox/pypowerwall:${VER} | grep Platform
  echo ""
  echo "* VERIFY jasonacox/pypowerwall:latest"
  docker buildx imagetools inspect jasonacox/pypowerwall | grep Platform
  echo ""

  # Restore link for testing
  rm -rf pypowerwall
  ln -s ../pypowerwall pypowerwall

else
  # Exit script if last_path is not "proxy"
  echo "Current directory is not 'proxy'."
  exit 0
fi
