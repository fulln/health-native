
const copyButton=document.querySelector('.copy');
const copyStatus=document.querySelector('.status');
let clearStatus;
copyButton.addEventListener('click',async()=>{
  clearTimeout(clearStatus);
  try{await navigator.clipboard.writeText(copyButton.dataset.copy);copyStatus.textContent='已复制';}
  catch{copyStatus.textContent='请长按上方校验值手动复制';}
  clearStatus=setTimeout(()=>{copyStatus.textContent='';},3000);
});
