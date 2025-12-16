#!/bin/bash
# Script to run tailor-image in Docker for local development
# This script automates the process of logging into AWS ECR, pulling the latest tailor-image,
# and running it with the necessary environment variables and volume mounts.

set -e  # Exit on error

# Configuration
AWS_REGION="us-east-1"
AWS_PROFILE="locus_ansible"
ECR_REGISTRY="084758475884.dkr.ecr.us-east-1.amazonaws.com/locus-tailor"
IMAGE_PREFIX="tailor-image-hotdog-parent-"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored messages
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}


print_info "Logging into AWS ECR..."
ECR_PASSWORD=$(aws ecr get-login-password --region ${AWS_REGION} --profile ${AWS_PROFILE})
if [ -z "$ECR_PASSWORD" ]; then
    print_error "Failed to get ECR password. Please check your AWS credentials."
    exit 1
fi

if ! echo "${ECR_PASSWORD}" | docker login --username AWS --password-stdin ${ECR_REGISTRY}; then
    print_error "Failed to login to AWS ECR. Please check your AWS credentials."
    exit 1
fi
print_info "Successfully logged into AWS ECR"


print_info "Finding latest ${IMAGE_PREFIX}* image..."

# Use jq to parse JSON and find the latest image by semantic version
LATEST_TAG=$(aws ecr describe-images \
    --repository-name locus-tailor \
    --region ${AWS_REGION} \
    --profile ${AWS_PROFILE} \
    --output json | \
    jq -r '.imageDetails[] | select(.imageTags != null) | .imageTags[] | select(startswith("'${IMAGE_PREFIX}'"))' | \
    sort -V | tail -1)

if [ -z "$LATEST_TAG" ] || [ "$LATEST_TAG" == "null" ]; then
    print_error "Could not find any images matching pattern '${IMAGE_PREFIX}*'"
    exit 1
fi

FULL_IMAGE_NAME="${ECR_REGISTRY}:${LATEST_TAG}"
print_info "Found latest image: ${LATEST_TAG}"

# Echo the full docker pull command for debugging
print_info "Pulling Docker image: ${FULL_IMAGE_NAME}"
echo "Running: docker pull ${FULL_IMAGE_NAME}"

if ! docker pull ${FULL_IMAGE_NAME}; then
    print_error "Failed to pull Docker image."
    exit 1
fi
print_info "Successfully pulled Docker image"


print_info "Checking environment variables..."

# Check AWS credentials from ~/.aws/credentials
if [ -z "$AWS_ACCESS_KEY_ID" ] || [ -z "$AWS_SECRET_ACCESS_KEY" ]; then
    print_warning "AWS credentials not set in environment. Attempting to read from ~/.aws/credentials..."

    if [ -f ~/.aws/credentials ]; then
        # Extract credentials for locus_ansible profile
        AWS_ACCESS_KEY_ID=$(grep -A 2 "\[${AWS_PROFILE}\]" ~/.aws/credentials | grep aws_access_key_id | cut -d'=' -f2 | tr -d ' ')
        AWS_SECRET_ACCESS_KEY=$(grep -A 2 "\[${AWS_PROFILE}\]" ~/.aws/credentials | grep aws_secret_access_key | cut -d'=' -f2 | tr -d ' ')

        if [ -n "$AWS_ACCESS_KEY_ID" ] && [ -n "$AWS_SECRET_ACCESS_KEY" ]; then
            export AWS_ACCESS_KEY_ID
            export AWS_SECRET_ACCESS_KEY
            print_info "AWS credentials loaded from ~/.aws/credentials"
        else
            print_error "Could not find AWS credentials for profile '${AWS_PROFILE}' in ~/.aws/credentials"
            exit 1
        fi
    else
        print_error "~/.aws/credentials file not found"
        exit 1
    fi
fi



# Step 5: Check for required directories
print_info "Checking for required directories..."

ROSDISTRO_PATH="${HOME}/locus_dev/src/rosdistro"
TAILOR_IMAGE_PATH="${HOME}/locus_dev/src/tailor-image"

if [ ! -d "$ROSDISTRO_PATH" ]; then
    print_warning "rosdistro directory not found at ${ROSDISTRO_PATH}"
    print_warning "The container will start but you may need to adjust volume mounts."
fi

if [ ! -d "$TAILOR_IMAGE_PATH" ]; then
    print_warning "tailor-image directory not found at ${TAILOR_IMAGE_PATH}"
    print_warning "Using current directory: $(pwd)"
    TAILOR_IMAGE_PATH="$(pwd)"
fi

# Step 6: Run the Docker container
print_info "Starting Docker container..."
print_info "Once inside, run the following commands:"
echo ""
echo "  1. Install tailor-image:"
echo "     sudo pip3 install -e tailor-image"
echo ""
echo "  2. Create an image (example):"
echo "     sudo -E create_image --name bot --distribution jammy \\"
echo "       --apt-repo locus-tailor-artifacts --release-track hotdog \\"
echo "       --release-label hotdog --flavour bot --organization locusrobotics \\"
echo "       --publish --docker-registry https://084758475884.dkr.ecr.us-east-1.amazonaws.com/locus-tailor \\"
echo "       --rosdistro-path /rosdistro"
echo ""
echo "     (You can change the --name arg to match your rosdistro's config/image.yaml)"
echo ""

# Build the docker run command
DOCKER_RUN_CMD="docker run -u tailor:tailor -it \
  --cap-add=ALL \
  --privileged \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /lib/modules:/lib/modules \
  -v /boot:/boot \
  -v /dev:/dev \
  --env AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID} \
  --env AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}"

# Add GITHUB_TOKEN if set
if [ -n "$GITHUB_TOKEN" ]; then
    DOCKER_RUN_CMD="${DOCKER_RUN_CMD} --env GITHUB_TOKEN=${GITHUB_TOKEN}"
fi

# Add volume mounts
DOCKER_RUN_CMD="${DOCKER_RUN_CMD} \
  -v ${ROSDISTRO_PATH}:/rosdistro \
  -v ${TAILOR_IMAGE_PATH}:/tailor-image \
  ${FULL_IMAGE_NAME} \
  bash"

# Execute the docker run command
#eval ${DOCKER_RUN_CMD}
