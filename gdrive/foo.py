from auth import WRITE_SCOPES, drive_service                          
import json                                                                   
                                                                              
svc = drive_service(scopes=WRITE_SCOPES)                                    
fid = '1VrlOpgeaUELN7Sf3Imeu2hHJGoyark4j'                                     
meta = svc.files().get(                                            
     fileId=fid,                                                    
     fields='id,name,parents,ownedByMe,capabilities,driveId,spaces',
     supportsAllDrives=True,      
).execute()                                                                   
print(json.dumps(meta, indent=2))                                  
