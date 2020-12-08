$(function () {
    function get_node_by_id(node_id) {
      return $('#mapcontext_tree').jstree(true).get_node(node_id);
    }
    function get_base_url(node_id) {
      let mapContextId = $('#mapcontext_tree').data("mapcontext-id");
      return '/resource/mapcontext/' + mapContextId  +'/folders';
    }
    function get_node_name(node) {
        let name = node.text.trim();
        if (name !== 'root') {
          return name;
        }
        return '';
    }
    function get_folder_path(node) {
      let path = '';
      while (node.parent && node.parent !== '#') {
        node = get_node_by_id(node.parent);
        path = get_node_name(node) + "/" + path;
      }
      return path;
    }
    function url_encode_folder_path(path) {
      console.log(path  + " -> " + path.split('/').map(component => encodeURIComponent(component)).join('/'));
      return path.split('/').map(component => encodeURIComponent(component)).join('/');
    }
    $('#mapcontext_tree').jstree({
      "core" : {
        "check_callback" : function (operation, node, node_parent, node_position, more) {
			// operation can be 'create_node', 'rename_node', 'delete_node', 'move_node', 'copy_node' or 'edit'
			// in case of 'rename_node' node_position is filled with the new node name
			if (operation === 'move_node') {
			   return typeof node_parent.text !== 'undefined';
			}
			return true;
		}
      },
      "plugins" : [ "dnd", "types", "unique", "rename", "actions", "contextmenu" ],
      "dnd" : {
        "copy": false,
      },
      "types" : {
        "root" : {
          "icon" : "fas fa-folder",
          "valid_children" : ["default","resource"]
        },
        "default" : {
          "icon" : "fas fa-folder",
          "valid_children" : ["default","resource"]
        },
        "resource" : {
          "icon" : "fas fa-map",
          "valid_children" : []
        }
      }
    }).on('create_node.jstree', function (e, data) {
        let folderPath = get_folder_path(data.node);
        let bodyData = {
          name : data.node.text
        }
        $.ajax({
          type: 'POST',
          url: get_base_url() + url_encode_folder_path(folderPath),
          contentType: 'application/json',
          data: JSON.stringify(bodyData),
        }).done(function () {
          // TODO id?
          data.instance.set_id(data.node, Date.now());
        }).fail(function () {
          data.instance.refresh();
        });
    }).on('rename_node.jstree', function (e, data) {
        let folderPath = get_folder_path(data.node) + data.old;
        let bodyData = {
          name : data.text
        }
        $.ajax({
          type: 'PUT',
          url: get_base_url() + url_encode_folder_path(folderPath),
          contentType: 'application/json',
          data: JSON.stringify(bodyData),
        }).fail(function () {
          data.instance.refresh();
        });
    }).on('delete_node.jstree', function (e, data) {
        let folderPath = get_folder_path(data.node) + data.node.text;
        $.ajax({
          type: 'DELETE',
          url: get_base_url() + url_encode_folder_path(folderPath)
        }).fail(function () {
          data.instance.refresh();
        })
    });
    $('#mapcontext_tree').jstree(true).add_action("all", {
        "id": "action_remove",
        "class": "fas fa-minus-circle",
        "title": "Remove Child",
        "after": true,
        "selector": "a",
        "event": "click",
        "callback": function (node_id, node, action_id, action_el) {
          let jstree = $('#mapcontext_tree').jstree(true);
          jstree.delete_node(node);
        }
    });
    $('#mapcontext_tree').jstree(true).add_action("all", {
        "id": "action_add_folder",
        "class": "fas fa-plus-circle",
        "title": "Add Folder",
        "after": true,
        "selector": "a",
        "event": "click",
        "callback": function (node_id, node, action_id, action_el) {
          let jstree = $('#mapcontext_tree').jstree(true);
          jstree.create_node(node, {}, "last", function (new_node) {
            try {
              jstree.edit(new_node);
            } catch (ex) {
              setTimeout(function () { inst.edit(new_node); },0);
            }
          });
        }
    });
    $('#mapcontext_tree').jstree(true).add_action("all", {
        "id": "action_add_layer",
        "class": "fas fa-map",
        "title": "Add WMS Layer",
        "after": true,
        "selector": "a",
        "event": "click",
        "callback": function (node_id, node, action_id, action_el) {
          //$( '#id_modal_' ).modal( 'hide' );
          $( '#id_modal_wmsresource' ).modal( 'show' );
          $('#id_modal_wmsresource .btn-primary').off('click');
          $('#id_modal_wmsresource .btn-primary').click(function (e) {
              let jstree = $('#mapcontext_tree').jstree(true);
              let childNode = {
                text : $('#id_modal_wmsresource').find('input[name="wms_layer"]').val(),
                type : "resource"
              };
              jstree.create_node(node, childNode, "last", function (new_node) {
                $( '#id_modal_wmsresource' ).modal( 'hide' );
              });
            });
          }
    });
//    $('#id_modal_wmsresource').on('hidden.bs.modal', function() {
//        $( '#id_modal_' ).modal( 'show' );
//    });
    $('#mapcontext_tree').jstree(true).add_action("all", {
        "id": "action_edit",
        "class": "fas fa-edit",
        "title": "Edit",
        "after": true,
        "selector": "a",
        "event": "click",
        "callback": function (node_id, node, action_id, action_el) {
          let jstree = $('#mapcontext_tree').jstree(true);
          jstree.edit(node.id);
        }
    });
    $('#mapcontext_tree').on("changed.jstree", function (e, data) {
      console.log(data.selected);
    });
    $('#mapcontext_tree').on('move_node.jstree', function (e, data) {
      //debugger;
      let path = data.node.text;
      let oldParent = get_node_by_id(data.old_parent);
      path = get_folder_path(oldParent) + get_node_name(oldParent) + '/' + path;

      let target = get_folder_path(data.node);
      // position = 0 -> use parent as reference and use 'first-child'
      let position = 'first-child';
      if (data.position > 0) {
        // position > 0 -> use my left sibling as reference and use 'right'
        let parent = get_node_by_id(data.parent);
        left_sibling = get_node_by_id(parent.children[data.position - 1]);
        target = target + get_node_name(left_sibling);
        position = 'right'
        console.log ('first-child: ' + target);
      }
      console.log ('move to ' + target + " (" + position + ")");
      let bodyData = {
        target : target,
        position : position
      }
      $.ajax({
        type: 'PUT',
        url: get_base_url() + url_encode_folder_path(path),
        contentType: 'application/json',
        data: JSON.stringify(bodyData),
      }).fail(function () {
        data.instance.refresh();
      });
    });
});

/*
$("#tree").on("loaded.jstree", function(){
                var select = document.getElementById("p2").getElementsByTagName("a")[0];
                var copy = select.getElementsByTagName("i")[0];
                var copyt = select.textContent;
                select.innerHTML= "";
                var btn = document.createElement("BUTTON");
                var t = document.createTextNode("CLICK ME");
                btn.appendChild(t);
                select.appendChild(copy);
                select.appendChild(btn);
                select.appendChild(document.createTextNode(copyt));
            });
*/
/*
$('#mapcontext_tree').jstree(true).add_action("all", {
    "id": "action_remove",
    "class": "action_remove pull-right",
    "title": "Remove Node",
    "text": "asa",
    "after": true,
    "selector": "a",
    "event": "click",
    "callback": function(node_id, node, action_id, action_el){
        console.log("callback", node_id, action_id);
    }
})
*/

