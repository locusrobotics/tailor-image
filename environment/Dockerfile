FROM ubuntu:bionic

LABEL tailor="environment"

ARG AWS_ACCESS_KEY_ID
ENV AWS_ACCESS_KEY_ID ${AWS_ACCESS_KEY_ID}

ARG AWS_SECRET_ACCESS_KEY
ENV AWS_SECRET_ACCESS_KEY ${AWS_SECRET_ACCESS_KEY}

ARG AWS_DEFAULT_REGION=us-east-1

ARG GITHUB_TOKEN
ENV GITHUB_TOKEN ${GITHUB_TOKEN}

ARG ANSIBLE_VAULT_PASS
ARG APT_REPO
ARG RELEASE_LABEL
ARG RELEASE_TRACK
ARG ORGANIZATION
ARG FLAVOUR
ENV BUNDLE_ROOT /opt/${ORGANIZATION}/${RELEASE_LABEL}/${FLAVOUR}

SHELL ["/bin/bash", "-c"]

ENV DEBIAN_FRONTEND noninteractive
ENV PYTHONUNBUFFERED 1

RUN apt-get update && apt-get install --no-install-recommends -y locales curl gnupg1 gpgv1 sudo
RUN locale-gen en_US.UTF-8
ENV LANG en_US.UTF-8

RUN apt-get update && apt-get install --no-install-recommends -y \
  python3-dev \
  python3-pip \
  python3-setuptools \
  python3-wheel \
  git

# Let's start with some basic stuff.
RUN apt-get update -qq && apt-get install -qqy \
    ansible \
    apt-transport-https \
    ca-certificates \
    curl \
    gcc \
    iptables \
    libguestfs-tools \
    lxc \
    openssh-client \
    unzip \
    wget \
    xz-utils

# Install Docker from Docker Inc. repositories.
RUN curl -sSL https://get.docker.com/ | VERSION=5:20.10.5 sh

# Install packer
RUN curl -sSL https://releases.hashicorp.com/packer/1.4.1/packer_1.4.1_linux_amd64.zip > packer.zip && \
    unzip packer.zip -d /usr/local/bin && \
    rm packer.zip
RUN curl -sSlL https://github.com/summerwind/packer-builder-qemu-chroot/releases/download/v1.1.0/packer-builder-qemu-chroot_linux_amd64.tar.gz > packer_qemu_chroot.tar.gz && \
    tar xf packer_qemu_chroot.tar.gz && mv packer-builder-qemu-chroot /usr/local/bin/packer-builder-qemu-chroot && \
    rm packer_qemu_chroot.tar.gz

COPY tailor-image tailor-image
RUN pip3 install -e tailor-image

COPY rosdistro/rosdep/rosdep.yaml /root/rosdep.yaml
COPY rosdistro /rosdistro

# Create non-root user
RUN groupadd -r tailor && useradd -ms /bin/bash -g tailor -G sudo tailor
RUN usermod -aG docker tailor
RUN echo "tailor ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers

# Add package mirror
# TODO(pbovbel) read this from configuration
RUN apt-get update && apt-get install -y apt-transport-https apt-transport-s3 && \
    apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 142D5F1683E1528B

RUN wget -O /usr/lib/apt/methods/s3 https://raw.githubusercontent.com/locusrobotics/apt-transport-s3/https/s3 && \
    echo "deb [arch=amd64] ${APT_REPO}/${RELEASE_LABEL}/ubuntu bionic main" >> /etc/apt/sources.list && \
    echo "deb [arch=amd64] ${APT_REPO}/${RELEASE_LABEL}/ubuntu bionic-mirror main" >> /etc/apt/sources.list

# Create auth config file for accesing s3 via apt
RUN echo "AccessKeyId = $AWS_ACCESS_KEY_ID" | tee /etc/apt/s3auth.conf && \
    echo "SecretAccessKey = $AWS_SECRET_ACCESS_KEY" | tee -a /etc/apt/s3auth.conf && \
    echo "Token = ''" | tee -a /etc/apt/s3auth.conf

RUN apt-get update && \
    RTI_NC_LICENSE_ACCEPTED=yes apt-get install -qy\
    python-catkin-tools \
    ${ORGANIZATION}-${FLAVOUR}-${RELEASE_LABEL}

USER tailor

RUN mkdir -p /home/tailor && \
    usermod -d /home/tailor tailor

RUN echo "${ANSIBLE_VAULT_PASS}" | tee /home/tailor/.vault_pass.txt
RUN aws configure set aws_access_key_id ${AWS_ACCESS_KEY_ID} && \
    aws configure set aws_secret_access_key ${AWS_SECRET_ACCESS_KEY} && \
    aws configure set default.region ${AWS_DEFAULT_REGION}
