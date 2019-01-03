#!/usr/bin/env groovy

// Learn groovy: https://learnxinyminutes.com/docs/groovy/

def docker_credentials = 'ecr:us-east-1:tailor_aws'
def recipes_config = 'rosdistro/config/recipes.yaml'

def days_to_keep = 10
def num_to_keep = 10

def testImage = { distribution, docker_registry -> docker_registry - "https://" + ':tailor-image-' + distribution + '-test-image' }

def distributions = []

pipeline {
  agent none

  parameters {
    string(name: 'rosdistro_job', defaultValue: '/ci/rosdistro/master')
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

          distributions = readYaml(file: recipes_config)['os'].collect {
            os, distribution -> distribution }.flatten()

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
          def jobs = distributions.collectEntries { distribution ->
            [distribution, {node('master') {
              try {
                dir('tailor-image') {
                  checkout(scm)
                }

                withCredentials([[$class: 'AmazonWebServicesCredentialsBinding', credentialsId: 'tailor_aws']]) {
                  test_image = docker.build(testImage(params.docker_registry, distribution),
                    "-f tailor-image/environment/Dockerfile --no-cache " +
                    "--build-arg OS_VERSION=" + distribution + " " +
                    "--build-arg APT_REPO=" + (params.apt_repo - 's3://') + " " +
                    "--build-arg AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID " +
                    "--build-arg AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY .")
                }
                docker.withRegistry(params.docker_registry, docker_credentials) {
                  if(params.deploy) {
                    test_image.push()
                  }
                }
              } finally {
                deleteDir()
                sh 'docker image prune -af --filter="until=3h" --filter="label=tailor" || true'
              }
            }}]
          }
          parallel(jobs)
        }
      }
    }
  }
}
