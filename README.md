# tailor-image

## Installation

```bash
pip install -e .
```

## Core Functionality

### create_image.py

The main entry point for image creation. Supports multiple storage modes and image types.

#### Basic Usage

```bash
create_image --name <image_name> --distribution <ubuntu_version> [options]
```

#### Required Arguments

- `--name`: Name of the image to build
- `--distribution`: Ubuntu distribution (e.g., jammy, focal, noble)

#### Optional Arguments

- `--apt-repo`: APT repository URL for package sources
- `--release-track`: Release track for naming and organization
- `--release-label`: Release label for versioning
- `--flavour`: Bundle flavour to install
- `--organization`: Organization name for image metadata
- `--docker-registry`: Docker registry URL for container images
- `--rosdistro-path`: Path to ROS distribution configuration files
- `--timestamp`: Custom timestamp (default: current time)

#### Storage Mode Arguments

- `--publish`: Upload images to S3 (production mode)
- `--build-only`: Build image but don't upload anywhere
- `--local-storage`: Store images locally instead of S3
- `--local-storage-path`: Local storage path (default: ./images)

## Storage Modes

### 1. Build-Only Mode

Creates images locally without uploading to any remote storage.

```bash
create_image --name wrangler --distribution jammy --build-only
```

**Use cases:**
- Development and testing
- Offline environments
- Quick prototyping

**Output:** Images remain in the local `images/` directory

### 2. Local Storage Mode

Builds images and stores them in a local directory with proper organization and indexing.

```bash
create_image --name wrangler --distribution jammy --local-storage --local-storage-path /opt/images
```

**Use cases:**
- Local image repositories for development


**Output structure:**
```
/opt/images/
├── release_label/
│   └── images/
│       ├── index.json                    # Image index
│       ├── org_name_dist_label_time.tar.gz  # LXD images
│       ├── org_name_dist_label_time.raw.xz  # Bare metal images
│       └── org_name_dist_label_time.md5     # Checksums
```

### 3. S3 Mode (Production)

Uploads images to AWS S3 with CloudFront integration.

```bash
create_image --name wrangler --distribution jammy --publish --apt-repo s3://bucket-name
```



## Image Types

### Docker Images

Container images built for development and testing environments.



**Configuration:** `environment/image_recipes/docker/docker.json`



## Configuration




## Examples

### Development Workflow

```bash
# Build a development image locally
create_image --name dev-env --distribution jammy --build-only

# Test the image
# ... testing procedures ...

# Build and store in local repository
create_image --name dev-env --distribution jammy --local-storage --local-storage-path /opt/local-images

# Deploy to production S3
create_image --name dev-env --distribution jammy --publish --apt-repo s3://prod-images
```


### Container Deployment

```bash
# Build LXD image
create_image --name webapp --distribution jammy --local-storage --local-storage-path /var/lib/images

# Import into LXD
lxc image import /var/lib/images/release/images/org_webapp_jammy_release_timestamp.tar.gz --alias webapp:latest
```
