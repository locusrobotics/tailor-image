#!/usr/bin/env groovy

// Learn groovy: https://learnxinyminutes.com/docs/groovy/

def docker_registry = '084758475884.dkr.ecr.us-east-1.amazonaws.com/tailor-image'
def docker_registry_uri = 'https://' + docker_registry
def docker_credentials = 'ecr:us-east-1:tailor_aws'

def days_to_keep = 10
def num_to_keep = 10

def testImage = { distribution -> docker_registry + ':jenkins-' + distribution + '-test-image' }

pipeline {
  agent none

  parameters {
    string(name: 'rosdistro_source', defaultValue: 'master')
    string(name: 'release_track', defaultValue: 'hotdog')
    string(name: 'release_label', defaultValue: 'hotdog')
    string(name: 'num_to_keep', defaultValue: '10')
    string(name: 'days_to_keep', defaultValue: '10')
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
          library("tailor-meta")
          cancelPreviousBuilds()

          // TODO(pbovbel) straighten out how this works
          deploy = env.BRANCH_NAME == 'master' ? true : false

          properties([
            buildDiscarder(logRotator(
              daysToKeepStr: params.days_to_keep, numToKeepStr: params.num_to_keep,
              artifactDaysToKeepStr: params.days_to_keep, artifactNumToKeepStr: params.num_to_keep
            ))
          ])

          copyArtifacts(projectName: "/ci/rosdistro/" + params.rosdistro_source)
          stash(name: 'rosdistro', includes: 'rosdistro/**')
        }
      }
      post {
        cleanup {
          deleteDir()
        }
      }
    }

    stage("Create test image") {
      agent any
      steps {
        script {
          dir('tailor-upstream') {
            checkout(scm)
          }
          def distribution = 'xenial'
          def test_image = docker.image(testImage(distribution))
          try {
            docker.withRegistry(docker_registry_uri, docker_credentials) { test_image.pull() }
          } catch (all) {
            echo "Unable to pull ${testImage(distribution)} as a build cache"
          }

          withCredentials([[$class: 'AmazonWebServicesCredentialsBinding', credentialsId: 'tailor_aws']]) {
            test_image = docker.build(testImage(distribution),
              "-f tailor-image/environment/Dockerfile --cache-from ${testImage(distribution)} " +
              "--build-arg AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID " +
              "--build-arg AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY .")
          }
          docker.withRegistry(docker_registry_uri, docker_credentials) {
            test_image.push()
          }
        }
      }
      post {
        cleanup {
          deleteDir()
          sh 'docker image prune -af --filter="until=3h" --filter="label=tailor" || true'
        }
      }
    }
  }
}


@NonCPS
def cancelPreviousBuilds() {
    def jobName = env.JOB_NAME
    def buildNumber = env.BUILD_NUMBER.toInteger()
    /* Get job name */
    def currentJob = Jenkins.instance.getItemByFullName(jobName)

    /* Iterating over the builds for specific job */
    for (def build : currentJob.builds) {
        /* If there is a build that is currently running and it's older than current build */
        if (build.isBuilding() && build.number.toInteger() < buildNumber) {
            /* Than stopping it */
            build.doStop()
        }
    }
}
