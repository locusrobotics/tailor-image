FROM ubuntu:noble

LABEL tailor="environment"

ARG ANSIBLE_VAULT_PASS
ARG APT_REPO
ARG APT_REGION
ARG RELEASE_LABEL
ARG ORGANIZATION
ARG FLAVOUR

ARG AWS_ACCESS_KEY_ID
ARG AWS_SECRET_ACCESS_KEY
ARG AWS_DEFAULT_REGION=us-east-1
ARG GITHUB_TOKEN
ARG APT_REFRESH_KEY

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=en_US.UTF-8 \
    PYTHONUNBUFFERED=1 \
    BUNDLE_PATH=/opt/${ORGANIZATION}/${RELEASE_LABEL}/${FLAVOUR} \
    AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID} \
    AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY} \
    GITHUB_TOKEN=${GITHUB_TOKEN}

SHELL ["/bin/bash", "-c"]

RUN echo "APT refresh key=${APT_REFRESH_KEY}"
RUN sed -i 's/archive.ubuntu.com/us-east-1.ec2.&/g' /etc/apt/sources.list && \
    apt-get update && apt-get install --no-install-recommends -y \
    locales \
    curl \
    gnupg1 \
    gpgv1 \
    sudo \
    python3-dev \
    python3-pip \
    python3-setuptools \
    python3-wheel \
    git \
    ansible \
    apt-transport-https \
    ca-certificates \
    debootstrap \
    gcc \
    git \
    gnupg1 \
    gpgv1 \
    iptables \
    libguestfs-tools \
    lxc \
    openssh-client \
    python3-dev \
    python3-pip \
    python3-setuptools \
    python3-wheel \
    sudo \
    unzip \
    wget \
    xz-utils && \
    locale-gen en_US.UTF-8 && \
    rm -rf /var/lib/apt/lists/*

# Install Docker from Docker Inc. repositories.
RUN curl -sSL https://get.docker.com/ | VERSION=28.0.0 sh

# Install packer
RUN curl -sSL https://releases.hashicorp.com/packer/1.9.1/packer_1.9.1_linux_amd64.zip > packer.zip && \
    unzip packer.zip -d /usr/local/bin && \
    rm packer.zip && \
    curl -sSlL https://github.com/locusrobotics/packer-builder-qemu-chroot/releases/download/v1.1.0-u1/packer-builder-qemu-chroot_linux_amd64.tar.gz > packer_qemu_chroot.tar.gz && \
    tar xf packer_qemu_chroot.tar.gz && mv packer-plugin-qemu-chroot /usr/local/bin/packer-plugin-qemu-chroot && \
    rm packer_qemu_chroot.tar.gz

COPY rosdistro/rosdep/rosdep.yaml /root/rosdep.yaml
COPY rosdistro /rosdistro

COPY tailor-image tailor-image
RUN pip3 install --break-system-packages -e tailor-image

# Add package mirror
RUN apt-get update && apt-get install --no-install-recommends -y apt-transport-https apt-transport-s3 && \
    apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 142D5F1683E1528B && \
    echo "deb [arch=amd64] ${APT_REPO}/${RELEASE_LABEL}/ubuntu noble main" >> /etc/apt/sources.list && \
    echo "deb [arch=amd64] ${APT_REPO}/${RELEASE_LABEL}/ubuntu noble-mirror noble" >> /etc/apt/sources.list

# Create auth config file for accesing s3 via apt
RUN echo "AccessKeyId = $AWS_ACCESS_KEY_ID" | tee /etc/apt/s3auth.conf && \
    echo "SecretAccessKey = $AWS_SECRET_ACCESS_KEY" | tee -a /etc/apt/s3auth.conf && \
    echo "Token = ''" | tee -a /etc/apt/s3auth.conf && \
    echo "Region = '${APT_REGION}'" | tee -a /etc/apt/s3auth.conf

RUN apt-get update && \
    RTI_NC_LICENSE_ACCEPTED=yes apt-get install --no-install-recommends -qy\
    ${ORGANIZATION}-${FLAVOUR}-${RELEASE_LABEL}  && \
    rm -rf /var/lib/apt/lists/*

RUN pip3 install --break-system-packages -U catkin_tools

# Create non-root user
ARG USER_NAME=tailor
RUN usermod -md "/home/$USER_NAME" -s /bin/bash -l $USER_NAME ubuntu && \
    groupmod -n $USER_NAME ubuntu && \
    usermod -aG docker "$USER_NAME" && \
    echo "$USER_NAME ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers

USER ${USER_NAME}
WORKDIR /home/${USER_NAME}

RUN echo "${ANSIBLE_VAULT_PASS}" | tee /home/tailor/.vault_pass.txt && \
    aws configure set aws_access_key_id ${AWS_ACCESS_KEY_ID} && \
    aws configure set aws_secret_access_key ${AWS_SECRET_ACCESS_KEY} && \
    aws configure set default.region ${AWS_DEFAULT_REGION}
