#!/usr/bin/env groovy

// Learn groovy: https://learnxinyminutes.com/docs/groovy/

def docker_credentials = 'ecr:us-east-1:tailor_aws'
def recipes_yaml = 'rosdistro/config/recipes.yaml'
def images_yaml = 'rosdistro/config/images.yaml'

def testImage = { distribution, release_label, docker_registry, image_name -> docker_registry - "https://" + ':tailor-image-'+ image_name + '-' + distribution + '-' + release_label }
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
    string(name: 'docker_registry')
    string(name: 'apt_repo')
    booleanParam(name: 'deploy', defaultValue: false)
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

          images = readYaml(file: images_yaml).images

          stash(name: 'rosdistro', includes: 'rosdistro/**')
        }
      }
      post {
        cleanup {
          deleteDir()
        }
      }
    }

    stage("Build and test tailor-image") {
      agent any
      steps {
        script {
          dir('tailor-image') {
            checkout(scm)
          }
          stash(name: 'source', includes: 'tailor-image/**')
          def parent_image_label = parentImage(params.release_label, params.docker_registry)
          def parent_image = docker.image(parent_image_label)
          try {
            docker.withRegistry(params.docker_registry, docker_credentials) { parent_image.pull() }
          } catch (all) {
            echo("Unable to pull ${parent_image_label} as a build cache")
          }

          unstash(name: 'rosdistro')
          withCredentials([[$class: 'AmazonWebServicesCredentialsBinding', credentialsId: 'tailor_aws']]) {
            parent_image = docker.build(parent_image_label,
              "-f tailor-image/environment/Dockerfile --cache-from ${parent_image_label} " +
              "--build-arg AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID " +
              "--build-arg AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY .")
          }

          parent_image.inside() {
            sh('cd tailor-image && python3 setup.py test')
          }
          docker.withRegistry(params.docker_registry, docker_credentials) {
            parent_image.push()
          }
        }
      }
      post {
        always {
          junit(testResults: 'tailor-image/test-results.xml')
        }
        cleanup {
          deleteDir()
          // If two docker prunes run simultaneously, one will fail, hence || true
          sh('docker image prune -af --filter="until=3h" --filter="label=tailor" || true')
        }
      }
    }

    stage("Create images") {
      agent none
      steps {
        script {
          def jobs = new LinkedHashMap()
          distributions.each { distribution ->
            jobs << images.collectEntries { image, config ->
              ["${image}-${distribution}", { node {
                try {
                  dir('tailor-image') {
                    checkout(scm)
                  }
                  unstash(name: 'rosdistro')

                  def parent_image = docker.image(parentImage(params.release_label, params.docker_registry))
                  docker.withRegistry(params.docker_registry, docker_credentials) {
                    parent_image.pull()
                  }

                  withCredentials([[$class: 'AmazonWebServicesCredentialsBinding', credentialsId: 'tailor_aws']]) {
                    parent_image.inside("-v /var/run/docker.sock:/var/run/docker.sock --privileged " +
                                        "--env AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID " +
                                        "--env AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY") {
                      sh( "sudo -E create_image --name ${image} --build-type ${config['build_type']} " +
                          " --package ${config['package']} --provision-file ${config['provision_file']} " +
                          " --distribution ${distribution} --apt-repo ${params.apt_repo - 's3://'} " +
                          " --release_track ${params.release_track} --flavour ${testing_flavour} " +
                          " --organization ${organization} ${params.deploy ? '--publish' : ''}")
                    }
                  }
                } finally {
                  deleteDir()
                  sh 'docker image prune -af --filter="until=3h" --filter="label=tailor" || true'
                }
              }}]
            }
          }
          parallel(jobs)
        }
      }
    }
  }
}
