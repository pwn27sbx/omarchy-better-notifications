import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "hero-notifications"

  implicitWidth: 24
  implicitHeight: root.bar ? root.bar.barSize : 28

  property bool opened: false
  property string historyDir: Quickshell.env("HOME") + "/.local/state/omarchy/notifications/history"

  function colorForApp(appName) {
    var colors = [Color.accent, Color.urgent, "#89b4fa", "#a6e3a1", "#f9e2af", "#f38ba8", "#cba6f7", "#94e2d5", "#f2cdcd", "#b4befe"]
    if (!appName) return colors[0]
    var hash = 0
    for (var i = 0; i < appName.length; i++) {
      hash = appName.charCodeAt(i) + ((hash << 5) - hash)
    }
    return colors[Math.abs(hash) % colors.length]
  }

  function timeAgo(ts) {
    if (!ts) return "now"
    var diff = Math.floor((Date.now() - ts) / 1000)
    if (diff < 60) return "now"
    if (diff < 3600) return Math.floor(diff / 60) + "m"
    if (diff < 86400) return Math.floor(diff / 3600) + "h"
    return Math.floor(diff / 86400) + "d"
  }

  property bool isDnd: false
  property bool showSettings: false
  property bool splitScreenshots: true // Activado por defecto
  property int currentTab: 0 // 0 = Alertas, 1 = Screenshots

  // --- Sistema de Idioma Interno ---
  property string lang: Qt.locale().name.substring(0, 2)
  property var i18nDict: ({
    "es": {
      "Notifications": "Notificaciones",
      "Muted": "Silenciado",
      "TOTAL": "TOTAL",
      "Clear all": "Limpiar todo",
      "Separate Captures": "Separar Capturas",
      "Alerts": "Alertas",
      "Captures": "Capturas",
      "ALERTS": "ALERTAS",
      "CAPTURES": "CAPTURAS",
      "HISTORY": "HISTORIAL",
      "No notifications": "No tienes notificaciones"
    },
    "en": {
      "Notifications": "Notifications",
      "Muted": "Muted",
      "TOTAL": "TOTAL",
      "Clear all": "Clear all",
      "Separate Captures": "Separate Captures",
      "Alerts": "Alerts",
      "Captures": "Captures",
      "ALERTS": "ALERTS",
      "CAPTURES": "CAPTURES",
      "HISTORY": "HISTORY",
      "No notifications": "No notifications"
    }
  })

  function tr(key) {
    var dict = i18nDict[lang] || i18nDict["en"]
    return dict[key] || key
  }
  // ---------------------------------

  property string settingsFile: historyDir + "/../hero_settings.json"

  Process {
    id: loadSettingsProc
    command: ["cat", settingsFile]
    running: true
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        try {
          var cfg = JSON.parse(text)
          if (cfg.splitScreenshots !== undefined) root.splitScreenshots = cfg.splitScreenshots
        } catch(e) {}
      }
    }
  }

  Process {
    id: saveSettingsProc
    property bool val: false
    command: ["bash", "-c", "echo '{\"splitScreenshots\":' + (val?'true':'false') + '}' > " + settingsFile]
  }

  onSplitScreenshotsChanged: {
    saveSettingsProc.val = splitScreenshots
    saveSettingsProc.running = true
  }

  Process {
    id: dndChecker
    command: ["omarchy-shell", "notifications", "dndState"]
    running: true
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        if (text) {
          root.isDnd = (text.trim() === "on")
        }
      }
    }
  }

  Timer {
    interval: 2000
    running: true
    repeat: true
    onTriggered: dndChecker.running = true
  }

  function toggle() {
    opened = !opened
    if (opened) {
      reader.running = true
      dndChecker.running = true
    } else {
      showSettings = false
    }
  }

  ListModel { id: historyModel }
  ListModel { id: generalModel }
  ListModel { id: mediaModel }

  property var activeModel: splitScreenshots ? (currentTab === 0 ? generalModel : mediaModel) : historyModel

  Process {
    id: reader
    command: ["bash", "-c", "cat " + historyDir + "/*.json 2>/dev/null | jq -s '.' 2>/dev/null || echo '[]'"]
    running: false
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        var parsed = []
        try { parsed = JSON.parse(text) } catch(e) {}
        
        var general = []
        var media = []
        for (var i = 0; i < parsed.length; i++) {
          var n = parsed[i]
          n.app = n.app || "Sistema" // Normalizar
          
          var isMedia = false
          var appStr = String(n.app).toLowerCase()
          var sumStr = String(n.summary || "").toLowerCase()
          
          if (appStr === "omarchy-action" && (sumStr.indexOf("screenshot") !== -1 || sumStr.indexOf("screenrecording") !== -1 || sumStr.indexOf("captura") !== -1 || sumStr.indexOf("grabación") !== -1)) {
            isMedia = true
            // Extraer la ruta de la imagen desde execArgv si no viene en el campo image
            if (!n.image && n.execArgv) {
              try {
                var args = JSON.parse(n.execArgv)
                if (Array.isArray(args) && args.length > 1) {
                  var filepath = args[args.length - 1]
                  if (filepath.indexOf(".png") !== -1 || filepath.indexOf(".jpg") !== -1) {
                    n.image = filepath
                  }
                }
              } catch(e) {}
            }
          }

          if (root.splitScreenshots && isMedia) {
            media.push(n)
          } else {
            general.push(n)
          }
        }

        var sortGrouped = function(arr) {
          var appLatest = {}
          for (var i = 0; i < arr.length; i++) {
            var a = arr[i].app
            var t = arr[i].timestamp || 0
            if (!appLatest[a] || t > appLatest[a]) appLatest[a] = t
          }
          arr.sort(function(a, b) {
            if (a.app !== b.app) return appLatest[b.app] - appLatest[a.app]
            return (b.timestamp || 0) - (a.timestamp || 0)
          })
          return arr
        }

        general = sortGrouped(general)
        media = sortGrouped(media)

        historyModel.clear()
        generalModel.clear()
        mediaModel.clear()

        for (var j = 0; j < parsed.length; j++) historyModel.append(parsed[j])
        for (var k = 0; k < general.length; k++) generalModel.append(general[k])
        for (var l = 0; l < media.length; l++) mediaModel.append(media[l])
        
        reader.running = false
      }
    }
  }

  WidgetButton {
    id: button
    width: 24
    height: parent.height
    anchors.verticalCenter: parent.verticalCenter
    anchors.horizontalCenter: parent.horizontalCenter
    anchors.horizontalCenterOffset: -1 // Ajuste milimétrico para alinear el centro visual de la campana con la rayita
    bar: root.bar
    text: root.isDnd ? "\uf1f6" : "\uf0f3" // bell-slash : bell
    horizontalMargin: 0 
    active: root.opened || (historyModel.count > 0 && !root.isDnd)
    tooltipText: root.tr("Notifications") + " (" + historyModel.count + ")" + (root.isDnd ? " - " + root.tr("Muted") : "")

    onPressed: function(mouse) { root.toggle() }
  }

  PopupCard {
    id: popup
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    
    contentWidth: popup.fittedContentWidth(Style.space(380))
    contentHeight: popup.fittedContentHeight(Style.space(550))

    function close() { root.opened = false }

    Item {
      anchors.fill: parent
      anchors.margins: Style.space(8) // Margen global ajustado para aprovechar más el espacio

      // Encabezado principal
      Item {
        id: headerTitle
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        height: Style.space(32)

        Row {
          anchors.left: parent.left
          anchors.verticalCenter: parent.verticalCenter
          spacing: Style.space(8)

          Text {
            anchors.verticalCenter: parent.verticalCenter
            text: "\uf0f3" // bell
            font.family: Style.font.family
            font.pixelSize: Math.round(Style.font.iconLarge * 1.3)
            color: Color.accent
          }

          Column {
            anchors.verticalCenter: parent.verticalCenter
            spacing: 0
            
            Text {
              text: root.tr("Notifications")
              font.bold: true
              font.pixelSize: Style.font.subtitle
              color: bar ? bar.foreground : Color.foreground
            }
            Text {
              text: historyModel.count + " " + root.tr("TOTAL")
              font.pixelSize: Style.font.caption
              color: bar ? bar.foreground : Color.foreground
              opacity: 0.5
              visible: historyModel.count > 0
            }
          }
        }

        Row {
          anchors.right: parent.right
          anchors.verticalCenter: parent.verticalCenter
          spacing: Style.space(10)

          // Toggle Switch DND
          Rectangle {
            anchors.verticalCenter: parent.verticalCenter
            width: Style.space(28)
            height: Style.space(16)
            radius: Style.cornerRadius
            color: root.isDnd ? Color.urgent : (bar ? Qt.rgba(bar.foreground.r, bar.foreground.g, bar.foreground.b, 0.2) : Qt.rgba(1,1,1,0.2))
            border.width: 1
            border.color: bar ? Qt.rgba(bar.foreground.r, bar.foreground.g, bar.foreground.b, 0.1) : "transparent"
            
            Behavior on color { ColorAnimation { duration: 150 } }
            
            Rectangle {
              width: parent.height - Style.space(4)
              height: parent.height - Style.space(4)
              radius: Style.cornerRadius > 0 ? Math.max(0, Style.cornerRadius - 2) : 0
              color: bar ? bar.background : Color.background
              y: Style.space(2)
              x: root.isDnd ? parent.width - width - Style.space(2) : Style.space(2)

              Behavior on x { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }
            }

            MouseArea {
              anchors.fill: parent
              cursorShape: Qt.PointingHandCursor
              onClicked: function() {
                // Actualización optimista para que la interfaz se sienta instantánea sin lag
                root.isDnd = !root.isDnd
                
                if (root.bar) {
                  root.bar.run("omarchy-shell notifications toggleDnd")
                  // Quitamos dndChecker.running = true aquí para evitar leer el estado viejo 
                  // antes de que toggleDnd termine de procesar en el sistema.
                }
              }
            }
          }

          // Botón Configuración (Engranaje)
          Text {
            anchors.verticalCenter: parent.verticalCenter
            text: "\uf013" // cog
            font.family: Style.font.family
            font.pixelSize: Style.font.iconLarge
            color: root.showSettings ? Color.accent : (bar ? bar.foreground : Color.foreground)
            opacity: root.showSettings ? 1.0 : 0.6
            
            MouseArea {
              anchors.fill: parent
              cursorShape: Qt.PointingHandCursor
              onClicked: root.showSettings = !root.showSettings
            }
          }
        }
      }

      // Panel de Configuración Desplegable
      Rectangle {
        id: settingsArea
        anchors.top: headerTitle.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.topMargin: root.showSettings ? Style.space(8) : 0
        height: root.showSettings ? Style.space(34) : 0
        opacity: root.showSettings ? 1 : 0
        visible: opacity > 0
        clip: true

        Behavior on height { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }
        Behavior on opacity { NumberAnimation { duration: 150 } }
        Behavior on anchors.topMargin { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }

        color: bar ? Qt.rgba(bar.foreground.r, bar.foreground.g, bar.foreground.b, 0.04) : Qt.rgba(1,1,1,0.04)
        radius: Style.cornerRadius
        border.width: 1
        border.color: bar ? Qt.rgba(bar.foreground.r, bar.foreground.g, bar.foreground.b, 0.1) : "transparent"

        Item {
          anchors.fill: parent
          anchors.margins: Style.space(8)

          Text {
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            text: root.tr("Separate Captures")
            font.pixelSize: Style.font.bodySmall
            color: bar ? bar.foreground : Color.foreground
          }

          Rectangle {
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            width: Style.space(28)
            height: Style.space(16)
            radius: Style.cornerRadius
            color: root.splitScreenshots ? Color.accent : (bar ? Qt.rgba(bar.foreground.r, bar.foreground.g, bar.foreground.b, 0.2) : Qt.rgba(1,1,1,0.2))
            
            Behavior on color { ColorAnimation { duration: 150 } }
            
            Rectangle {
              width: parent.height - Style.space(4)
              height: parent.height - Style.space(4)
              radius: Style.cornerRadius > 0 ? Math.max(0, Style.cornerRadius - 2) : 0
              color: bar ? bar.background : Color.background
              y: Style.space(2)
              x: root.splitScreenshots ? parent.width - width - Style.space(2) : Style.space(2)

              Behavior on x { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }
            }

            MouseArea {
              anchors.fill: parent
              cursorShape: Qt.PointingHandCursor
              onClicked: root.splitScreenshots = !root.splitScreenshots
            }
          }
        }
      }

      // Sistema de Pestañas (Tabs)
      Row {
        id: tabBar
        anchors.top: settingsArea.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.topMargin: root.splitScreenshots ? Style.space(8) : 0
        height: root.splitScreenshots ? Style.space(26) : 0
        opacity: root.splitScreenshots ? 1 : 0
        visible: opacity > 0
        spacing: Style.space(8)

        Behavior on height { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }
        Behavior on opacity { NumberAnimation { duration: 150 } }
        Behavior on anchors.topMargin { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }

        // Pestaña Alerts
        Rectangle {
          width: (parent.width - Style.space(8)) / 2
          height: parent.height
          radius: Style.cornerRadius
          color: root.currentTab === 0 ? Qt.rgba(Color.accent.r, Color.accent.g, Color.accent.b, 0.15) : "transparent"
          border.width: 1
          border.color: root.currentTab === 0 ? Color.accent : (bar ? Qt.rgba(bar.foreground.r, bar.foreground.g, bar.foreground.b, 0.1) : "transparent")

          Text {
            anchors.centerIn: parent
            text: root.tr("Alerts") + " (" + generalModel.count + ")"
            font.pixelSize: Style.font.bodySmall
            font.bold: root.currentTab === 0
            color: root.currentTab === 0 ? Color.accent : (bar ? bar.foreground : Color.foreground)
            opacity: root.currentTab === 0 ? 1.0 : 0.6
          }

          MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: root.currentTab = 0
          }
        }

        // Pestaña Screenshots
        Rectangle {
          width: (parent.width - Style.space(8)) / 2
          height: parent.height
          radius: Style.cornerRadius
          color: root.currentTab === 1 ? Qt.rgba(Color.urgent.r, Color.urgent.g, Color.urgent.b, 0.15) : "transparent"
          border.width: 1
          border.color: root.currentTab === 1 ? Color.urgent : (bar ? Qt.rgba(bar.foreground.r, bar.foreground.g, bar.foreground.b, 0.1) : "transparent")

          Text {
            anchors.centerIn: parent
            text: root.tr("Captures") + " (" + mediaModel.count + ")"
            font.pixelSize: Style.font.bodySmall
            font.bold: root.currentTab === 1
            color: root.currentTab === 1 ? Color.urgent : (bar ? bar.foreground : Color.foreground)
            opacity: root.currentTab === 1 ? 1.0 : 0.6
          }

          MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: root.currentTab = 1
          }
        }
      }

      // Línea separadora
      Rectangle {
        id: separator
        anchors.top: tabBar.visible ? tabBar.bottom : settingsArea.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.topMargin: Style.space(8)
        height: 1
        color: bar ? Qt.rgba(bar.foreground.r, bar.foreground.g, bar.foreground.b, 0.1) : Qt.rgba(1, 1, 1, 0.1)
      }

      // Sección "HISTORY" con botón Clear all
      Item {
        id: sectionHeader
        anchors.top: separator.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.topMargin: Style.space(8)
        height: Style.space(16)
        visible: activeModel.count > 0

        Text {
          anchors.left: parent.left
          anchors.verticalCenter: parent.verticalCenter
          text: root.splitScreenshots ? (root.currentTab === 0 ? root.tr("ALERTS") : root.tr("CAPTURES")) : root.tr("HISTORY")
          font.pixelSize: Style.font.caption
          font.bold: true
          color: bar ? bar.foreground : Color.foreground
          opacity: 0.5
        }

        Text {
          anchors.right: parent.right
          anchors.verticalCenter: parent.verticalCenter
          text: root.tr("Clear all")
          font.pixelSize: Style.font.bodySmall
          color: bar ? bar.foreground : Color.foreground
          opacity: 0.5
          
          MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            hoverEnabled: true
            onEntered: parent.opacity = 0.9
            onExited: parent.opacity = 0.5
            onClicked: function() {
              if (root.bar) {
                root.bar.run("omarchy-shell notifications clear")
                historyModel.clear()
                generalModel.clear()
                mediaModel.clear()
              }
            }
          }
        }
      }

      // Lista de notificaciones agrupadas
      ListView {
        id: listView
        anchors.top: sectionHeader.visible ? sectionHeader.bottom : separator.bottom
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.topMargin: Style.space(8)
        model: activeModel
        clip: true
        spacing: Style.space(2)
        
        // Agrupador por App
        section.property: "app"
        section.criteria: ViewSection.FullString
        section.delegate: Item {
          width: ListView.view.width
          height: Style.space(32)
          
          Row {
            anchors.left: parent.left
            anchors.leftMargin: Style.space(4)
            anchors.bottom: parent.bottom
            anchors.bottomMargin: Style.space(4)
            spacing: Style.space(8)
  
            Text {
              anchors.bottom: parent.bottom
              text: section.charAt(0).toUpperCase() + section.slice(1)
              font.pixelSize: Style.font.bodySmall
              font.bold: true
              color: root.colorForApp(section)
            }
          }
        }
  
        delegate: Item {
          id: delegateContainer
          width: ListView.view.width
          height: isDeleted ? 0 : delegateBg.height
          clip: true
          property bool isDeleted: false
          
          Behavior on height { NumberAnimation { duration: 200; easing.type: Easing.OutQuad } }

          Rectangle {
            id: delegateBg
            width: parent.width
            height: contentCol.implicitHeight + Style.space(12)
            color: "transparent"
            radius: Style.cornerRadius
            
            Behavior on x {
              id: xBehavior
              enabled: false
              NumberAnimation { duration: 200; easing.type: Easing.OutQuad }
            }

            MouseArea {
              anchors.fill: parent
              acceptedButtons: Qt.LeftButton | Qt.RightButton
              cursorShape: Qt.PointingHandCursor
              hoverEnabled: true
              
              drag.target: delegateBg
              drag.axis: Drag.XAxis
              drag.minimumX: -delegateContainer.width
              drag.maximumX: delegateContainer.width

              onEntered: delegateBg.color = bar ? Qt.rgba(bar.foreground.r, bar.foreground.g, bar.foreground.b, 0.06) : "rgba(255,255,255,0.06)"
              onExited: delegateBg.color = "transparent"
              
              onPressed: {
                xBehavior.enabled = false
              }
              
              onReleased: function(mouse) {
                if (Math.abs(delegateBg.x) > delegateContainer.width / 3) {
                  // Deslizó lo suficiente, salimos volando y borramos
                  xBehavior.enabled = true
                  delegateBg.x = (delegateBg.x > 0) ? delegateContainer.width : -delegateContainer.width
                  destroyTimer.start()
                } else if (delegateBg.x !== 0) {
                  // No deslizó lo suficiente, regresamos a la posición original
                  xBehavior.enabled = true
                  delegateBg.x = 0
                }
              }

              onClicked: function(mouse) {
                if (Math.abs(delegateBg.x) > 5) return

                if (mouse.button === Qt.RightButton) {
                  delegateContainer.isDeleted = true
                  deleteNotification()
                  return
                }
                
                var executed = false
                if (model.execArgv && model.execArgv.trim() !== "") {
                  try {
                    var cmdArray = JSON.parse(model.execArgv)
                    if (Array.isArray(cmdArray) && cmdArray.length > 0) {
                      var escapedStr = ""
                      for (var j = 0; j < cmdArray.length; j++) {
                        escapedStr += "'" + String(cmdArray[j]).replace(/'/g, "'\\''") + "' "
                      }
                      root.bar.run(escapedStr)
                      executed = true
                    }
                  } catch(e) {}
                } 
                
                if (!executed && model.app && model.app.trim() !== "") {
                  root.bar.run("/usr/share/omarchy/bin/omarchy-hyprland-focus-app '" + model.app.replace(/'/g, "'\\''") + "'")
                }
                root.opened = false
              }
            }

            Timer {
              id: destroyTimer
              interval: 200
              onTriggered: {
                delegateContainer.isDeleted = true
                deleteNotification()
              }
            }

            function deleteNotification() {
              root.bar.run("rm -f '" + root.historyDir + "/" + model.timestamp + "-" + model.originalId + ".json'")
              reloadTimer.start()
            }
            
            Timer {
              id: reloadTimer
              interval: 250
              onTriggered: reader.exec()
            }
          Image {
            id: appIconImg
            anchors.left: parent.left
            anchors.leftMargin: (model.app !== "omarchy-action") ? Style.space(8) : 0
            anchors.verticalCenter: contentCol.verticalCenter
            source: (model.appIcon && model.appIcon !== "") ? "image://icon/" + model.appIcon : ("image://icon/" + (model.app || "dialog-information"))
            width: (model.app !== "omarchy-action") ? Style.space(34) : 0
            height: (model.app !== "omarchy-action") ? Style.space(34) : 0
            sourceSize.width: Style.space(34)
            sourceSize.height: Style.space(34)
            smooth: true
            visible: (model.app !== "omarchy-action") && status === Image.Ready
          }
  
          Column {
            id: contentCol
            anchors.left: appIconImg.right
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.leftMargin: (model.app !== "omarchy-action") ? Style.space(10) : Style.space(12)
            anchors.rightMargin: Style.space(4)
            anchors.topMargin: Style.space(6)
            spacing: Style.space(4)
  
            // Fila superior: Summary y Tiempo
            Item {
              width: parent.width
              height: summaryTxt.implicitHeight
  
              Text {
                id: summaryTxt
                anchors.left: parent.left
                anchors.right: timeTxt.left
                anchors.rightMargin: Style.space(8)
                text: model.summary || ""
                font.pixelSize: Style.font.body
                font.bold: true
                color: bar ? bar.foreground : Color.foreground
                elide: Text.ElideRight
              }
  
              Text {
                id: timeTxt
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                text: root.timeAgo(model.timestamp)
                font.pixelSize: Style.font.caption
                color: bar ? bar.foreground : Color.foreground
                opacity: 0.4
              }
            }
  
            Text {
              width: parent.width
              text: model.body || ""
              font.pixelSize: Style.font.bodySmall
              color: bar ? bar.foreground : Color.foreground
              opacity: 0.7
              wrapMode: Text.Wrap
              maximumLineCount: 3
              elide: Text.ElideRight
              visible: text !== ""
            }
  
            // Thumbnail (Imagen adjunta)
            Rectangle {
              width: parent.width
              height: visible ? Style.space(120) : 0
              visible: model.image && model.image !== ""
              color: "transparent"
              radius: Math.max(0, Style.cornerRadius - 2)
              clip: true
  
              Image {
                anchors.fill: parent
                source: model.image ? (model.image.indexOf("file://") === 0 ? model.image : "file://" + model.image) : ""
                fillMode: Image.PreserveAspectCrop
                asynchronous: true
                smooth: true
              }
            }
          }
        }
        } // Cierra el delegateContainer Item
      }

      // Mensaje vacío
      Column {
        anchors.centerIn: parent
        visible: activeModel.count === 0
        spacing: Style.space(12)
        
        Text {
          anchors.horizontalCenter: parent.horizontalCenter
          text: "\uf0f3" // bell
          font.family: Style.font.family
          font.pixelSize: Math.round(Style.font.iconLarge * 2)
          color: bar ? bar.foreground : Color.foreground
          opacity: 0.2
        }
        
        Text {
          anchors.horizontalCenter: parent.horizontalCenter
          text: root.tr("No notifications") + " ✨"
          font.pixelSize: Style.font.body
          font.bold: true
          color: bar ? bar.foreground : Color.foreground
          opacity: 0.6
        }
      }
    }
  }
}
