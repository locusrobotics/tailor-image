#!/usr/bin/env groovy

// Learn groovy: https://learnxinyminutes.com/docs/groovy/

def docker_registry = '084758475884.dkr.ecr.us-east-1.amazonaws.com/tailor-image'
def docker_credentials = 'ecr:us-east-1:tailor_aws'

def release_track = 'hotdog'
def days_to_keep = 10
def num_to_keep = 10

timestamps {
  stage("Configure build parameters") {
    node('master') {
      cancelPreviousBuilds()
      sh 'env'

      // Why is this so complicated...
      def projectProperties = [
        [$class: 'BuildDiscarderProperty',
          strategy:
            [$class: 'LogRotator',
              artifactDaysToKeepStr: days_to_keep.toString(), artifactNumToKeepStr: num_to_keep.toString(),
              daysToKeepStr: days_to_keep.toString(), numToKeepStr: num_to_keep.toString()]],
        pipelineTriggers([
            upstream(upstreamProjects: '../tailor-distro/' + env.BRANCH_NAME, threshold: hudson.model.Result.SUCCESS)
        ]),
      ]
      properties(projectProperties)

      // TODO(pbovbel) detect if we should use a different bundle version
      // if env.CHANGE_TARGET.startsWith('release/') {
      //   release_track = env.CHANGE_TARGET - 'release/'
      // }

      test_bundle = "locusrobotics-dev-" + release_track

      // // Choose build type based on tag/branch name
      // if (env.TAG_NAME != null) {
      //   // Create tagged release
      //   release_track = env.TAG_NAME
      //   release_label = release_track + '-final'
      //   days_to_keep = null
      // } else if (env.BRANCH_NAME.startsWith('release/')) {
      //   // Create a release candidate
      //   release_track = env.BRANCH_NAME - 'release/'
      //   release_label = release_track + '-rc'
      //   days_to_keep = null
      // } else if (env.BRANCH_NAME == 'master') {
      //   // Create mystery meat package
      //   build_schedule = 'H H/3 * * *'
      // } else {
      //   // Create a feature package
      //   release_label = release_track + '-' + env.BRANCH_NAME
      // }
      // release_track = release_track.replaceAll("\\.", '-')
      // release_label = release_label.replaceAll("\\.", '-')
      //
      // // TODO(pbovbel) clean these up
      // def projectProperties = [
      //   [$class: 'BuildDiscarderProperty',
      //     strategy:
      //       [$class: 'LogRotator',
      //         artifactDaysToKeepStr: days_to_keep.toString(), artifactNumToKeepStr: num_to_keep.toString(),
      //         daysToKeepStr: days_to_keep.toString(), numToKeepStr: num_to_keep.toString()]],
      // ]
      // if (build_schedule) {
      //   projectProperties.add(pipelineTriggers([cron(build_schedule)]))
      // }
      // properties(projectProperties)
    }
  }

  // stage("Build and test" + env.JOB_NAME) {
  //   node {
  //     try {
  //       dir('package') {
  //         checkout(scm)
  //       }
  //       withCredentials([[$class: 'AmazonWebServicesCredentialsBinding', credentialsId: 'tailor_aws']]) {
  //         environment[parentImage(release_track)] = docker.build(parentImage(release_track), "-f tailor-upstream/environment/Dockerfile " +
  //           "--build-arg AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID " +
  //           "--build-arg AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY .")
  //       }
  //       environment[parentImage(release_track)].inside() {
  //         sh 'cd tailor-upstream && python3 setup.py test'
  //       }
  //       docker.withRegistry(docker_registry_uri, docker_credentials) {
  //         environment[parentImage(release_track)].push()
  //       }
  //       stash(name: 'upstream', includes: upstream_config_path)
  //     } finally {
  //       junit(testResults: 'tailor-upstream/test-results.xml', allowEmptyResults: true)
  //       deleteDir()
  //       // If two docker prunes run simulataneously, one will fail, hence || true
  //       sh 'docker image prune -af --filter="until=3h" --filter="label=tailor" || true'
  //     }
  //   }
  // }

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
