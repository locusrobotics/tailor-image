# TODO(pbovbel) read from rosdistro
FROM ubuntu:xenial

LABEL tailor="test_image"

SHELL ["/bin/bash", "-c"]

ARG AWS_ACCESS_KEY_ID
ENV AWS_ACCESS_KEY_ID ${AWS_ACCESS_KEY_ID}

ARG AWS_SECRET_ACCESS_KEY
ENV AWS_SECRET_ACCESS_KEY ${AWS_SECRET_ACCESS_KEY}

ENV DEBIAN_FRONTEND noninteractive
ENV PYTHONUNBUFFERED 1

RUN apt-get update && apt-get install --no-install-recommends -y locales sudo ccache
RUN locale-gen en_US.UTF-8
ENV LANG en_US.UTF-8

# TODO(pbovbel) repack boto to avoid pip hacks
RUN apt-get install -y python-all-dev python-pip python-setuptools python-wheel && \
		apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 379CE192D401AB61 && \
		echo "deb http://dl.bintray.com/lucidsoftware/apt/ lucid main" > /etc/apt/sources.list.d/boto-s3.list && \
		apt-get update && apt-get install -y apt-boto-s3

RUN apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 142D5F1683E1528B && \
	  echo 'deb [arch=amd64] s3://s3.amazonaws.com/tailor-mirror/ubuntu xenial hotdog' >> /etc/apt/sources.list.d/locus.list && \
		echo 'deb [arch=amd64] s3://s3.amazonaws.com/tailor-packages/ubuntu xenial hotdog' >> /etc/apt/sources.list.d/locus.list && \
 		apt-get update && apt-get dist-upgrade -y && \
		apt-get install -y locusrobotics-dev-hotdog python3-colcon-common-extensions python3-pkg-resources

# TODO(pbovbel) rosdep install dependencies of /workspace/src

# Create non-root user
RUN groupadd -r tailor && useradd -ms /bin/bash -g tailor -G sudo tailor
USER tailor

RUN mkdir -p /home/tailor && \
    usermod -d /home/tailor tailor

RUN ccache -M 5G && \
    ccache --set-config=cache_dir=/ccache

# # TODO(pbovbel) read from rosdistro
# CMD source /opt/locusrobotics/hotdog/dev/ros1/setup.bash && \
# 	  TERM=dumb colcon build \
# 			--base-paths /workspace/src \
# 			--build-base /tmp/colcon_build \
# 			--install-base /tmp/colcon_install \
# 			--cmake-args \
# 				-DCMAKE_CXX_FLAGS='-DNDEBUG -g -fext-numeric-literals' \
# 				-DCMAKE_CXX_STANDARD='14' \
# 				-DCMAKE_CXX_STANDARD_REQUIRED='ON' \
# 				-DCMAKE_CXX_EXTENSIONS='ON' \
# 				-DCMAKE_CXX_COMPILER_LAUNCHER=ccache \
# 			--merge-install && \
# 	  TERM=dumb colcon test \
# 			--base-paths /workspace/src \
# 			--build-base /tmp/colcon_build \
# 			--install-base /tmp/colcon_install \
# 			--test-result-base /workspace/test \
# 			--cmake-args \
# 				-DCMAKE_CXX_FLAGS='-DNDEBUG -g -fext-numeric-literals' \
# 				-DCMAKE_CXX_STANDARD='14' \
# 				-DCMAKE_CXX_STANDARD_REQUIRED='ON' \
# 				-DCMAKE_CXX_EXTENSIONS='ON' \
# 				-DCMAKE_CXX_COMPILER_LAUNCHER=ccache \
# 			--merge-install
