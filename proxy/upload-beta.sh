#!/bin/bash
echo "Build and Push jasonacox/pypowerwall to Docker Hub"
echo "Usage: $0 [beta_number]"
echo "  If beta_number is not provided, auto-increments from last beta version"
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
  
  # Handle beta numbering
  BETA_FILE=".beta_version"
  if [ -n "$1" ]; then
    # Use provided beta number
    BETA_NUM="$1"
    echo "$BETA_NUM" > "$BETA_FILE"
  else
    # Auto-increment beta number
    if [ -f "$BETA_FILE" ]; then
      BETA_NUM=$(cat "$BETA_FILE")
      BETA_NUM=$((BETA_NUM + 1))
    else
      BETA_NUM=1
    fi
    echo "$BETA_NUM" > "$BETA_FILE"
  fi
  
  VER="${PYPOWERWALL}${PROXY}-beta${BETA_NUM}"

  # Check with user before proceeding
  echo "Build and push jasonacox/pypowerwall:${VER} to Docker Hub?"
  echo "Beta version: ${BETA_NUM} (stored in ${BETA_FILE})"
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
