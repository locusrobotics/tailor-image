#!/usr/bin/env groovy

// Learn groovy: https://learnxinyminutes.com/docs/groovy/

def docker_credentials = 'ecr:us-east-1:tailor_aws'
def recipes_yaml = 'rosdistro/config/recipes.yaml'
def images_yaml = 'rosdistro/config/images.yaml'

def parentImage = { release, docker_registry -> docker_registry - "https://" + ':tailor-image-' + release + '-parent-' + env.BRANCH_NAME }

def distributions = []
def images = null
def organization = null
def testing_flavour = null

pipeline {
  agent none

  parameters {
    string(name: 'rosdistro_job', defaultValue: '/ci/toydistro/master')
    string(name: 'release_track', defaultValue: 'hotdog')
    string(name: 'release_label', defaultValue: 'hotdog')
    string(name: 'num_to_keep', defaultValue: '10')
    string(name: 'days_to_keep', defaultValue: '10')
    string(name: 'retries', defaultValue: '3')
    string(name: 'timestamp')
    string(name: 'docker_registry')
    string(name: 'tailor_meta')
    string(name: 'apt_repo')
    string(name: 'apt_region', defaultValue: 'us-east-1')
    booleanParam(name: 'deploy', defaultValue: false)
    booleanParam(name: 'invalidate_cache', defaultValue: false)
    string(name: 'apt_refresh_key')
    booleanParam(name: 'slack_notifications_enabled', defaultValue: false)
    string(name: 'slack_notifications_channel', defaultValue: '')
  }

  options {
    timestamps()
  }

  stages {
    stage("Configure build parameters") {
      agent { label('master') }
      steps {
        script {
          sh('env')

          properties([
            buildDiscarder(logRotator(
              daysToKeepStr: params.days_to_keep, numToKeepStr: params.num_to_keep,
              artifactDaysToKeepStr: params.days_to_keep, artifactNumToKeepStr: params.num_to_keep
            ))
          ])

          copyArtifacts(
            projectName: params.rosdistro_job,
            selector: upstream(fallbackToLastSuccessful: true),
          )

          // (pbovbel) Read configuration from rosdistro. This should probably happen in some kind of Python
          def recipes_config = readYaml(file: recipes_yaml)
          organization = recipes_config['common']['organization']
          testing_flavour = recipes_config['common']['testing_flavour']
          distributions = recipes_config['os'].collect {
            os, distribution -> distribution }.flatten()

          images_config = readYaml(file: images_yaml).images

          stash(name: 'rosdistro', includes: 'rosdistro/**')
        }
      }
      post {
        cleanup {
          deleteDir()
        }
      }
    }

    stage("Build tailor-image") {
      agent any
      steps {
        script {
          dir('tailor-image') {
            checkout(scm)
          }

          stash(name: 'source', includes: 'tailor-image/**')
          def parent_image_label = parentImage(params.release_label, params.docker_registry)
          def parent_image = docker.image(parent_image_label)
          withEnv(['DOCKER_BUILDKIT=1']) {
            try {
              docker.withRegistry(params.docker_registry, docker_credentials) { parent_image.pull() }
            } catch (all) {
              echo("Unable to pull ${parent_image_label} as a build cache")
            }

            unstash(name: 'rosdistro')
            withCredentials([[$class: 'AmazonWebServicesCredentialsBinding', credentialsId: 'tailor_aws'],
                              string(credentialsId: 'ansible_vault_password', variable: 'ANSIBLE_VAULT_PASS')]) {
              retry(params.retries as Integer) {
                parent_image = docker.build(parent_image_label,
                  "${params.invalidate_cache ? '--no-cache ' : ''}" +
                  "-f tailor-image/environment/Dockerfile --cache-from ${parent_image_label} " +
                  "--build-arg APT_REPO=${params.apt_repo} " +
                  "--build-arg APT_REGION=${params.apt_region} " +
                  "--build-arg RELEASE_LABEL=${params.release_label} " +
                  "--build-arg RELEASE_TRACK=${params.release_track} " +
                  "--build-arg FLAVOUR=${testing_flavour} " +
                  "--build-arg ORGANIZATION=${organization} " +
                  "--build-arg AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID " +
                  "--build-arg AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY " +
                  "--build-arg ANSIBLE_VAULT_PASS=$ANSIBLE_VAULT_PASS " +
                  "--build-arg BUILDKIT_INLINE_CACHE=1 " +
                  "--build-arg APT_REFRESH_KEY=${params.apt_refresh_key} .")
              }
            }

            parent_image.inside() {
              sh('pip3 install --break-system-packages -e tailor-image')
            }
            docker.withRegistry(params.docker_registry, docker_credentials) {
              parent_image.push()
            }
          }
        }
      }
      post {
        cleanup {
          library("tailor-meta@${params.tailor_meta}")
          cleanDocker()
          deleteDir()
        }
        failure {
          script  {
            FAILED_STAGE = "Build tailor-image"
          }
        }
      }
    }

    stage("Create images") {
      agent none
      steps {
        script {
          def jobs = [:]
          images_config.each { image, config ->
            def tmp_distributions = distributions.clone()

            // If `os_versions` is not configured, default to build for all distros
            if (config.containsKey('os_versions')) {
              tmp_distributions = config['os_versions'].findAll { it in distributions }
            }

            // If `bundle_flavour` not defined, default to testing_flavour
            def bundle_flavour = testing_flavour
            if (config.containsKey('bundle_flavour')) {
              bundle_flavour = config['bundle_flavour']
            }

            jobs << tmp_distributions.collectEntries { distribution ->
              ["${image}-${distribution}", { node {
                try {
                  retry(params.retries as Integer) {
                    dir('tailor-image') {
                      checkout(scm)
                    }
                    unstash(name: 'rosdistro')

                    def parent_image = docker.image(parentImage(params.release_label, params.docker_registry))
                    docker.withRegistry(params.docker_registry, docker_credentials) {
                      parent_image.pull()
                    }

                    withCredentials([[$class: 'AmazonWebServicesCredentialsBinding', credentialsId: 'tailor_aws']]) {
                      parent_image.inside("-v /var/run/docker.sock:/var/run/docker.sock -v /lib/modules:/lib/modules " +
                                          "-v /dev:/dev -v /boot:/boot --cap-add=ALL --privileged " +
                                          "--env AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID " +
                                          "--env AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY") {
                        sh("""#!/bin/bash
                              sudo -E create_image \
                              --name ${image} \
                              --distribution ${distribution} \
                              --apt-repo ${params.apt_repo - 's3://'} \
                              --release-track ${params.release_track} \
                              --release-label ${params.release_label} \
                              --flavour ${bundle_flavour} \
                              --organization ${organization} \
                              --docker-registry ${params.docker_registry} \
                              --rosdistro-path /rosdistro \
                              --timestamp ${params.timestamp} \
                              ${params.deploy ? '--publish' : ''}
                           """)
                      }
                    }
                  }
                } finally {
                  library("tailor-meta@${params.tailor_meta}")
                  try {
                    if (fileExists(".")) {
                    deleteDir()
                    }
                  } catch (e) {
                    println e
                  }
                  cleanDocker()
                }
              }}]
            }
          }
          parallel(jobs)
        }
      }
      post {
        failure {
          script  {
            FAILED_STAGE = "Create images"
          }
        }
      }
    }
  }
  // Slack bot to notify of any step failure
  post {
    failure {
      script {
        if (params.slack_notifications_enabled && (params.rosdistro_job == '/ci/rosdistro/master' || params.rosdistro_job.startsWith('/ci/rosdistro/release')))
        {
          slackSend(
            channel: params.slack_notifications_channel,
            color: 'danger',
            message: """
*Build failure* for `${params.release_label}` (<${env.RUN_DISPLAY_URL}|Open>)
*Sub-pipeline*: tailor-image
*Stage*: ${FAILED_STAGE ?: 'unknown'}
"""
          )
        }
      }
    }
  }
}
