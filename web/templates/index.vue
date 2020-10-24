<!DOCTYPE html>
<html>
<head>
  <link href="https://fonts.googleapis.com/css?family=Roboto:100,300,400,500,700,900" rel="stylesheet">
  <link href="https://cdn.jsdelivr.net/npm/@mdi/font@4.x/css/materialdesignicons.min.css" rel="stylesheet">
  <link href="https://cdn.jsdelivr.net/npm/vuetify@2.x/dist/vuetify.min.css" rel="stylesheet">
  <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, minimal-ui">
</head>
<body>
  <div id="app">
    <audio controls autoplay>
      <source src="{{stream_url}}" type="audio/ogg">
      Your browser does not support the audio tag.
    </audio>
    <v-app>
      <v-main>
        <v-container>Number of users: <span v-text="number_of_users"></span></v-container>
          <v-card
    class="mx-auto"
    tile
  >
            <v-card-title v-text="song">

            </v-card-title>
            [ <a :href="'/music/'+song">link</a> ]
            <v-progress-linear
                    v-model="progress"
                    color="purple"
            ></v-progress-linear>
            <v-card-text v-text="time"></v-card-text>

    <v-list disabled>
      <v-subheader>Playlist</v-subheader>
      <v-list-item-group
        color="primary"
      >
        <v-list-item
          v-for="(item, i) in queued"
          :key="item"
        >
          <v-list-item-content>
            <v-list-item-title v-text="item"></v-list-item-title>
          </v-list-item-content>
        </v-list-item>
      </v-list-item-group>
    </v-list></v-col></v-row>
              </v-container>
  </v-card>
            <v-list two-line>
          <v-list-item :key="item.text" v-for="item in messages">
              <v-list-item-content>
                <v-list-item-title v-text="item.name"></v-list-item-title>

                <v-list-item class="text--primary" v-text="item.text">

                </v-list-item>
              </v-list-item-content>

          </v-list-item>

    </v-list>
        <v-form ref="form" action="/upload" method="post" enctype="multipart/form-data" class="pa-4 pt-6">
      <v-text-field
        v-model="name"
        filled
        color="deep-purple"
        label="Name"
      ></v-text-field>
      <v-textarea
        v-model="text"
        auto-grow
        filled
        color="deep-purple"
        label="Message"
        rows="3"
      ></v-textarea>
            <v-file-input name="mp3"
  truncate-length="15" label="Mp3 file"
></v-file-input>
              <v-btn
      class="mr-4"
      @click="sendMessage"
    >
      submit
    </v-btn>
        </v-form>
      </v-main>
    </v-app>
  </div>

  <script src="https://cdn.jsdelivr.net/npm/vue@2.x/dist/vue.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/vuetify@2.x/dist/vuetify.js"></script>
  <script>
    new Vue({
      el: '#app',
      vuetify: new Vuetify(),
      data() {
        return {
          progress: 0, messages: [], song: '', time: '', queued: [], name: 'Anonymous', text: '', conn: null, number_of_users: 0
        };
      },
      mounted() {
        this.connect();
      },
        methods: {
        sendMessage: function (event) {
          if(document.querySelector('input[type="file"]').files.length) {
            document.forms[0].submit();
          }else{
            this.conn.send(JSON.stringify({'name': this.name, 'text': this.text}));
          }
        },
            connect: function () {
        let wsUri = (window.location.protocol=='https:'&&'wss://'||'ws://')+window.location.host;
        this.messages.push({name: 'debug', text:`connecting to ${wsUri}`});
        this.conn = new WebSocket(wsUri);
       this.conn.onopen = () => {
         this.messages.push({name: 'debug', text:`connected`});

        };
       this.conn.onmessage = (e) => {
            let data = JSON.parse(e.data);
            if(data.text) {
                this.messages.push(data);
                return;
            }
            switch (data.action) {
                // case  'connect':
                //     name = data.name;
                //     log('Connected as ' + name);
                //     update_ui();
                //     break;
                 case  'disconnect':
                     this.connect();
                     break;
                // case 'join':
                //     log('Joined ' + data.name);
                //     break;
                // case 'sent':
                //     log(data.name + ': ' + data.text);
                //     break;
                // case 'error':
                //     log('error');
                //     break;
                case 'np':
                    this.song = data.song;
                    this.progress = data.progress;
                    this.time = data.time;
                    this.queued = data.queued;
                    this.number_of_users = data.number_of_users;
                    break;
            }
        };
       this.conn.onclose = () => {
         this.connect();
        };
    }
        }
    })
  </script>
</body>
</html>
