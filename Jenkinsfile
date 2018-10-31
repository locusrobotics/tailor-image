#!/usr/bin/env groovy

// Learn groovy: https://learnxinyminutes.com/docs/groovy/

def docker_registry = '084758475884.dkr.ecr.us-east-1.amazonaws.com/locus-tailor'
def docker_registry_uri = 'https://' + docker_registry
def docker_credentials = 'ecr:us-east-1:tailor_aws'

def days_to_keep = 10
def num_to_keep = 10

def testImage = { distribution -> docker_registry + ':tailor-image-' + distribution + '-test-image-' + env.BRANCH_NAME }

pipeline {
  agent none

  parameters {
    string(name: 'rosdistro_job', defaultValue: '/ci/rosdistro/master')
    string(name: 'release_track', defaultValue: 'hotdog')
    string(name: 'release_label', defaultValue: 'hotdog')
    string(name: 'num_to_keep', defaultValue: '10')
    string(name: 'days_to_keep', defaultValue: '10')
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
          dir('tailor-image') {
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
            if(params.deploy) {
              test_image.push()
            }
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
