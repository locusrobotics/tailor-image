# tailor-image

Just a quick script to generate a docker image for package test pipines to use.

Long term all sorts of images...

- Docker
- LXD
- Bare metal

 ...should be generated here using something like Packer, for purposes of:

 - machine installation
 - developer use
 - automated test environments

## Cleanup behavior

The `s3_cleanup` command applies retention to two S3 areas under a release label:

- image artifacts under `{release_label}/images/`
- change logs under `{release_label}/changes/{YYYYMMDD.HHMMSS}/`

