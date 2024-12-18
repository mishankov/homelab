# ffmpeg examples

Add new audio to mkv

```shell
ffmpeg -i 'input video.mkv' \
-i 'input audio 0.mka'  \
-i 'input audio 1.mka' \
-i 'input audio 2.mka' \
-map 0 \
-map 1:a -metadata:s:a:1 title="audio 0" \
-map 2:a -metadata:s:a:2 title="audio 1" \
-map 3:a -metadata:s:a:3 title="audio 2" \
-c:v copy -shortest 'output video.mkv'

mv 'output video.mkv' 'input video.mkv'
```
