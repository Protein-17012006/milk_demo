# MediaMTX v1.21.3 configuration, rendered by infra/remote/install.sh.
# The double-brace placeholders below are filled from SSM Parameter Store; never commit real values.
logLevel: info
logDestinations: [stdout]
readTimeout: 10s
writeTimeout: 10s
writeQueueSize: 1024

authMethod: internal
authInternalUsers:
  # The relay at the store: may publish camera paths (cam-...) and nothing else.
  - user: {{PUBLISH_USER}}
    pass: {{PUBLISH_PASS}}
    ips: []
    permissions:
      - action: publish
        path: "~^cam-[a-z0-9-]+$"
  # A counting worker on a GPU machine elsewhere: may read camera paths and nothing else.
  - user: {{WORKER_USER}}
    pass: {{WORKER_PASS}}
    ips: []
    permissions:
      - action: read
        path: "~^cam-[a-z0-9-]+$"
  # Processes on this server: the counter reads, the replay test source publishes.
  - user: any
    pass:
    ips: ["127.0.0.1", "::1"]
    permissions:
      - action: publish
        path:
      - action: read
        path:
      - action: api
      - action: metrics

api: true
apiAddress: 127.0.0.1:9997
metrics: false
pprof: false
playback: false

# RTSP only on localhost; from the internet only RTSPS (TLS) is open.
rtsp: true
rtspTransports: [tcp]
rtspEncryption: "optional"
rtspAddress: 127.0.0.1:8554
rtspsAddress: :8322
rtspServerKey: /etc/mediamtx/server.key
rtspServerCert: /etc/mediamtx/server.crt
rtspAuthMethods: [basic]

rtmp: false
hls: false
webrtc: false

# SRT with a passphrase (AES) for links that drop packets, such as 4G.
srt: true
srtAddress: :8890

pathDefaults:
  srtPublishPassphrase: {{SRT_PASSPHRASE}}

# install.sh appends the store camera path (pulled on demand) when camera/url is set in SSM.
paths:
  all_others:
