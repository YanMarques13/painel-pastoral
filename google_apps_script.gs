/** Painel Pastoral V14 — ponte Google Forms <-> Railway.
 * Publique como Web App: Executar como "Eu"; acesso "Qualquer pessoa".
 */
function jsonOut(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
function chave(pid, tipo) { return 'FORM_' + String(pid) + '_' + String(tipo).toUpperCase(); }
function doGet() { return jsonOut({ok:true, mensagem:'Painel Pastoral V14 / Google Forms ativo'}); }
function doPost(e) {
  try {
    var d = JSON.parse((e.postData && e.postData.contents) || '{}');
    if (d.acao === 'criar_formulario') return criarFormulario(d);
    if (d.acao === 'ler_respostas') return lerRespostas(d);
    return jsonOut({ok:false, erro:'Ação inválida'});
  } catch (err) { return jsonOut({ok:false, erro:String(err && err.message ? err.message : err)}); }
}
function criarFormulario(d) {
  var pid = String(d.processoId || ''); var tipo = String(d.tipo || '');
  if (!pid || (tipo !== 'indicacao' && tipo !== 'votacao')) return jsonOut({ok:false, erro:'processoId/tipo inválidos'});
  var props = PropertiesService.getScriptProperties(); var k = chave(pid,tipo); var existente = props.getProperty(k);
  if (existente) {
    var f0=FormApp.openById(existente);
    return jsonOut({ok:true, form_id:f0.getId(), responder_url:f0.getPublishedUrl(), editar_url:f0.getEditUrl(), reutilizado:true});
  }
  var sufixo = tipo === 'indicacao' ? ' — Indicações' : ' — Votação';
  var f = FormApp.create(String(d.titulo || 'Comissão de Nomeações') + sufixo);
  f.setDescription(String(d.descricao || '') + (tipo==='indicacao' ? '\n\nInforme o nome de sua indicação.' : '\n\nSelecione o(s) nome(s) de sua escolha.'));
  f.setConfirmationMessage(tipo==='indicacao' ? 'Indicação registrada. Obrigado.' : 'Voto registrado. Obrigado.');
  if (tipo === 'indicacao') {
    f.addTextItem().setTitle('Nome indicado').setRequired(true);
  } else {
    var nomes = Array.isArray(d.candidatos) ? d.candidatos.map(String) : [];
    if (!nomes.length) return jsonOut({ok:false, erro:'Nenhum candidato recebido'});
    var max = Math.max(1, Number(d.maxVotos || 1));
    if (max === 1) f.addMultipleChoiceItem().setTitle('Escolha um nome').setChoiceValues(nomes).setRequired(true);
    else {
      var item=f.addCheckboxItem().setTitle('Escolha até ' + max + ' nomes').setChoiceValues(nomes).setRequired(true);
      item.setValidation(FormApp.createCheckboxValidation().requireSelectAtMost(max).build());
    }
  }
  props.setProperty(k, f.getId());
  return jsonOut({ok:true, form_id:f.getId(), responder_url:f.getPublishedUrl(), editar_url:f.getEditUrl()});
}
function lerRespostas(d) {
  var pid=String(d.processoId || ''); var tipo=String(d.tipo || ''); var id=PropertiesService.getScriptProperties().getProperty(chave(pid,tipo));
  if (!id) return jsonOut({ok:false, erro:'Formulário não encontrado para este processo'});
  var f=FormApp.openById(id); var rs=f.getResponses(); var saida=[];
  rs.forEach(function(r,idx){
    var ir=r.getItemResponses(); var resposta=ir.length ? ir[0].getResponse() : '';
    // getId pode não estar disponível em todos os ambientes; timestamp+índice mantém chave estável para o conjunto retornado.
    var rid=''; try { rid=String(r.getId() || ''); } catch(e) {}
    if (!rid) rid=Utilities.base64EncodeWebSafe(Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, pid+'|'+tipo+'|'+r.getTimestamp().toISOString()+'|'+idx+'|'+JSON.stringify(resposta)));
    if (tipo==='indicacao') saida.push({id:rid,nome:String(resposta || '').trim()});
    else saida.push({id:rid,nomes:Array.isArray(resposta)?resposta.map(String):[String(resposta)]});
  });
  return jsonOut({ok:true, respostas:saida, total:saida.length});
}
