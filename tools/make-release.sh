#!/bin/bash
#
# Script for building a release that includes the third-party
# dependencies for installation in an offline environment.
#
# Copyright 2023 Checkmarx
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

if [ $# -ne 2 ]
then
        echo "usage: $0 <version> <imgae tag>"
        echo
        echo "For example:"
        echo
        echo "$ ./make-release.sh 1.0.0 python:3.11.0-slim-bullseye"
        exit 1
fi

version=v$1
src_dir=CxMGMTaC-$1
src_dir_with_deps=${src_dir}-with-deps
wheels_dir=${src_dir_with_deps}/wheels
imagetag=$2

curl -L -o ${version}.zip https://github.com/james-bostock-cx/CxMGMTaC/archive/refs/tags/${version}.zip

unzip ${version}.zip

mv ${src_dir} ${src_dir_with_deps}
mkdir ${wheels_dir}

docker run -v $(realpath ${src_dir_with_deps}):/app/CxMGMTaC -v $(realpath ${wheels_dir}):/app/wheels -t ${imagetag} pip3 wheel -r /app/CxMGMTaC/requirements.txt -w /app/wheels

zip -r ${src_dir_with_deps}.zip ${src_dir_with_deps}

rm -rf ${src_dir_with_deps}
